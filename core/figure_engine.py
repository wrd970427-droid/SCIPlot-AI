"""Generic Figure Engine — catalog-driven end-to-end orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from core.code_generation_engine import CodeGenerationEngine
from core.execution_manager import ExecutionManager
from core.figure_registry import FigureRegistry
from core.qc_manager import QCManager
from core.requirement_engine import (
    GenericRequirementResponse,
    GenericRequirementStatus,
    RequirementEngine,
)
from core.specification_builder import SpecificationBuilder
from schemas.generic_figure_spec import GenericFigureSpecification

WORK_SCRIPT_NAME = "figure.R"


class FigureEngineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "success",
        "failure",
        "need_information",
        "unavailable",
        "unknown_figure",
    ]
    figure_definition_id: str = ""
    message: str = ""
    missing_fields: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    requirement: Optional[dict[str, Any]] = None
    spec: Optional[dict[str, Any]] = None
    r_script_path: str = ""
    output_files: list[str] = Field(default_factory=list)
    qc_report: Optional[dict[str, Any]] = None
    log: str = ""


class FigureEngine:
    """
    User Request → Registry → Requirement → Spec → Code → Execute → QC

    New figures need: catalog entry + strategy (when implemented).
    No per-figure Requirement/Workflow rewrite.
    """

    def __init__(
        self,
        *,
        registry: FigureRegistry | None = None,
        requirement_engine: RequirementEngine | None = None,
        specification_builder: SpecificationBuilder | None = None,
        code_engine: CodeGenerationEngine | None = None,
        execution_manager: ExecutionManager | None = None,
        qc_manager: QCManager | None = None,
    ) -> None:
        self.registry = registry or FigureRegistry()
        self.requirement_engine = requirement_engine or RequirementEngine()
        self.specification_builder = specification_builder or SpecificationBuilder()
        self.code_engine = code_engine or CodeGenerationEngine()
        self.execution_manager = execution_manager or ExecutionManager()
        self.qc_manager = qc_manager or QCManager()

    def run(
        self,
        figure_id: str,
        *,
        answers: dict[str, Any] | None = None,
        available_columns: list[str] | None = None,
        user_request: str = "",
        work_dir: str | Path | None = None,
        data_source: str | None = None,
        execute: bool = True,
    ) -> FigureEngineResult:
        # Unknown figure
        try:
            definition = self.registry.get_figure_definition(figure_id)
        except KeyError:
            return FigureEngineResult(
                status="unknown_figure",
                figure_definition_id=figure_id,
                message=f"Unknown figure_id: {figure_id}",
            )

        # Catalog-only / not executable
        if not self.registry.is_executable(figure_id):
            status = definition.implementation_status.value
            return FigureEngineResult(
                status="unavailable",
                figure_definition_id=figure_id,
                message=(
                    f"Figure cataloged but implementation unavailable "
                    f"(implementation_status={status})"
                ),
            )

        # Strategy must exist for code generation
        if figure_id not in self.code_engine.supported_figures():
            return FigureEngineResult(
                status="unavailable",
                figure_definition_id=figure_id,
                message=(
                    "Figure cataloged but implementation unavailable "
                    "(no code-generation strategy registered)"
                ),
            )

        requirement = self.requirement_engine.collect(
            definition,
            answers=answers,
            available_columns=available_columns,
            user_request=user_request,
        )
        if requirement.status is GenericRequirementStatus.NEED_INFORMATION:
            return FigureEngineResult(
                status="need_information",
                figure_definition_id=figure_id,
                message=requirement.message,
                missing_fields=requirement.missing_fields,
                questions=requirement.questions,
                requirement=requirement.model_dump(mode="json"),
            )

        try:
            spec = self.specification_builder.build(
                definition,
                requirement,
                data_source=data_source or (answers or {}).get("data_file"),
            )
        except ValueError as exc:
            return FigureEngineResult(
                status="failure",
                figure_definition_id=figure_id,
                message=str(exc),
                requirement=requirement.model_dump(mode="json"),
            )

        if work_dir is None:
            # Spec-only path (no execution)
            return FigureEngineResult(
                status="success",
                figure_definition_id=figure_id,
                message="Specification ready",
                requirement=requirement.model_dump(mode="json"),
                spec=spec.model_dump(mode="json"),
            )

        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        script_path = work / WORK_SCRIPT_NAME
        if data_source and not spec.data_source:
            spec = spec.model_copy(update={"data_source": str(Path(data_source).name)})

        try:
            self.code_engine.generate(spec, output_path=script_path)
        except Exception as exc:  # noqa: BLE001
            return FigureEngineResult(
                status="failure",
                figure_definition_id=figure_id,
                message=f"Code generation failed: {exc}",
                requirement=requirement.model_dump(mode="json"),
                spec=spec.model_dump(mode="json"),
            )

        if not execute:
            return FigureEngineResult(
                status="success",
                figure_definition_id=figure_id,
                message="R script generated",
                requirement=requirement.model_dump(mode="json"),
                spec=spec.model_dump(mode="json"),
                r_script_path=str(script_path),
            )

        execution = self.execution_manager.execute_figure(script_path, work)
        try:
            qc = self.qc_manager.run_qc(spec, work)
            qc_dump = qc.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            qc_dump = {"status": "failed", "message": str(exc)}

        artifacts = sorted(
            path.name for path in work.iterdir() if path.is_file() and path.name != "input.csv"
        )
        if execution.status != "success":
            return FigureEngineResult(
                status="failure",
                figure_definition_id=figure_id,
                message="Execution failed",
                requirement=requirement.model_dump(mode="json"),
                spec=spec.model_dump(mode="json"),
                r_script_path=str(script_path),
                output_files=artifacts,
                qc_report=qc_dump,
                log=execution.log,
            )

        return FigureEngineResult(
            status="success",
            figure_definition_id=figure_id,
            message="Figure generated",
            requirement=requirement.model_dump(mode="json"),
            spec=spec.model_dump(mode="json"),
            r_script_path=str(script_path),
            output_files=artifacts,
            qc_report=qc_dump,
            log=execution.log,
        )

    def render_from_spec(
        self,
        spec: GenericFigureSpecification | dict[str, Any],
        work_dir: str | Path,
        *,
        execute: bool = True,
    ) -> FigureEngineResult:
        """Regenerate R + QC from an existing GenericFigureSpecification (shared Refine path)."""
        if not isinstance(spec, GenericFigureSpecification):
            spec = GenericFigureSpecification.model_validate(spec)
        figure_id = spec.figure_definition_id
        if figure_id not in self.code_engine.supported_figures():
            return FigureEngineResult(
                status="unavailable",
                figure_definition_id=figure_id,
                message=(
                    "Figure cataloged but implementation unavailable "
                    "(no code-generation strategy registered)"
                ),
                spec=spec.model_dump(mode="json"),
            )

        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        script_path = work / WORK_SCRIPT_NAME
        try:
            self.code_engine.generate(spec, output_path=script_path)
        except Exception as exc:  # noqa: BLE001
            return FigureEngineResult(
                status="failure",
                figure_definition_id=figure_id,
                message=f"Code generation failed: {exc}",
                spec=spec.model_dump(mode="json"),
            )
        if not execute:
            return FigureEngineResult(
                status="success",
                figure_definition_id=figure_id,
                message="R script generated",
                spec=spec.model_dump(mode="json"),
                r_script_path=str(script_path),
            )
        execution = self.execution_manager.execute_figure(script_path, work)
        try:
            qc = self.qc_manager.run_qc(spec, work)
            qc_dump = qc.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            qc_dump = {"status": "failed", "message": str(exc)}
        artifacts = sorted(
            path.name for path in work.iterdir() if path.is_file() and path.name != "input.csv"
        )
        if execution.status != "success":
            return FigureEngineResult(
                status="failure",
                figure_definition_id=figure_id,
                message="Execution failed",
                spec=spec.model_dump(mode="json"),
                r_script_path=str(script_path),
                output_files=artifacts,
                qc_report=qc_dump,
                log=execution.log,
            )
        return FigureEngineResult(
            status="success",
            figure_definition_id=figure_id,
            message="Figure generated",
            spec=spec.model_dump(mode="json"),
            r_script_path=str(script_path),
            output_files=artifacts,
            qc_report=qc_dump,
            log=execution.log,
        )

    def collect_requirements(
        self,
        figure_id: str,
        *,
        answers: dict[str, Any] | None = None,
        available_columns: list[str] | None = None,
        user_request: str = "",
    ) -> GenericRequirementResponse | FigureEngineResult:
        try:
            definition = self.registry.get_figure_definition(figure_id)
        except KeyError:
            return FigureEngineResult(
                status="unknown_figure",
                figure_definition_id=figure_id,
                message=f"Unknown figure_id: {figure_id}",
            )
        return self.requirement_engine.collect(
            definition,
            answers=answers,
            available_columns=available_columns,
            user_request=user_request,
        )

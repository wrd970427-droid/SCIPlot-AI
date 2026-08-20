"""End-to-end volcano figure workflow. Orchestration only — no plotting logic here."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from agents.volcano_r_code_agent import VolcanoRCodeAgent
from agents.volcano_requirement_agent import RequirementStatus, VolcanoRequirementAgent
from core.column_mapper import map_columns_from_request
from llm.intent_parser import IntentParser
from llm.llm_client import LLMError
from llm.r_code_editor import RCodeEditor, looks_like_science_transform
from qc.figure_qc_agent import FigureQCAgent
from refinement.refinement_agent import RefinementAgent
from schemas.figure_intent import FigureIntent, IntentFigureType, IntentPurpose
from schemas.figure_modification import FigureModification
from schemas.figure_spec import FigureSpecification
from schemas.spec_history import SpecHistory
from services.r_executor import ExecutionResult, execute_r_script

ExecuteFn = Callable[..., ExecutionResult]

ALLOWED_SUFFIXES = {".csv", ".tsv"}
WORK_INPUT_NAME = "input.csv"
WORK_SCRIPT_NAME = "volcano.R"
HISTORY_NAME = "spec_history.json"

INTENT_TO_FIGURE_ID = {
    IntentFigureType.SCATTER: "basic_statistics.scatter",
    IntentFigureType.BOXPLOT: "basic_statistics.boxplot",
    IntentFigureType.VIOLIN: "basic_statistics.boxplot",
}


class WorkflowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "failure", "need_information", "unmatched"]
    intent: Optional[dict[str, Any]] = None
    spec: Optional[dict[str, Any]] = None
    previous_spec: Optional[dict[str, Any]] = None
    modifications: list[dict[str, Any]] = Field(default_factory=list)
    history: Optional[dict[str, Any]] = None
    previous_version: int = 0
    current_version: int = 0
    r_script_path: str = ""
    output_files: list[str] = Field(default_factory=list)
    qc_report: Optional[dict[str, Any]] = None
    questions: list[str] = Field(default_factory=list)
    missing_parameters: list[str] = Field(default_factory=list)
    message: str = ""
    log: str = ""


class FigureWorkflow:
    """Wire NLU → Requirement → Spec → R → QC, plus design Refinement loop."""

    def __init__(
        self,
        *,
        intent_parser: IntentParser | None = None,
        requirement_agent: VolcanoRequirementAgent | None = None,
        r_code_agent: VolcanoRCodeAgent | None = None,
        qc_agent: FigureQCAgent | None = None,
        refinement_agent: RefinementAgent | None = None,
        r_code_editor: RCodeEditor | None = None,
        execute_fn: ExecuteFn | None = None,
    ) -> None:
        self.intent_parser = intent_parser or IntentParser()
        self.requirement_agent = requirement_agent or VolcanoRequirementAgent()
        self.r_code_agent = r_code_agent or VolcanoRCodeAgent()
        self.qc_agent = qc_agent or FigureQCAgent()
        self.refinement_agent = refinement_agent or RefinementAgent()
        self.r_code_editor = r_code_editor or RCodeEditor()
        self.execute_fn = execute_fn or execute_r_script

    def generate_figure(
        self,
        user_prompt: str,
        uploaded_file: str | Path,
        work_dir: str | Path,
    ) -> WorkflowResult:
        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        source = Path(uploaded_file)

        prepared = self._prepare_input(source, work / WORK_INPUT_NAME)
        if prepared is not None:
            return prepared

        answers = self._answers_from_table(work / WORK_INPUT_NAME)
        headers = self._table_headers(work / WORK_INPUT_NAME)
        intent = self.intent_parser.parse(user_prompt, available_columns=headers)
        intent_dump = intent.model_dump(mode="json")
        (work / "intent.json").write_text(intent.model_dump_json(indent=2), encoding="utf-8")

        if intent.figure_type is IntentFigureType.VOLCANO:
            answers.update(self._answers_from_intent(intent))
            req = self.requirement_agent.handle(user_prompt, answers=answers, intent=intent)

            if req.status is RequirementStatus.UNSUPPORTED:
                return WorkflowResult(
                    status="failure",
                    intent=intent_dump,
                    message="Unsupported figure type",
                )

            if req.status is RequirementStatus.NEED_INFORMATION:
                return WorkflowResult(
                    status="need_information",
                    intent=intent_dump,
                    spec=req.specification,
                    questions=req.questions,
                    missing_parameters=req.missing_parameters,
                    message="Required information missing",
                )

            spec = FigureSpecification.model_validate(req.specification)
            spec.plot.data.source = WORK_INPUT_NAME
            return self._render_and_qc(spec, work, intent_dump=intent_dump, init_history=True)

        figure_id = INTENT_TO_FIGURE_ID.get(intent.figure_type)
        if figure_id:
            return self._run_generic_figure(
                figure_id,
                user_prompt=user_prompt,
                work=work,
                headers=headers,
                intent=intent,
                intent_dump=intent_dump,
            )

        return WorkflowResult(
            status="failure",
            intent=intent_dump,
            message=(
                f"Figure cataloged but implementation unavailable "
                f"(figure_type={intent.figure_type.value})"
            ),
        )

    def _run_generic_figure(
        self,
        figure_id: str,
        *,
        user_prompt: str,
        work: Path,
        headers: list[str],
        intent: FigureIntent,
        intent_dump: dict[str, Any],
    ) -> WorkflowResult:
        mapping = map_columns_from_request(
            user_prompt,
            headers,
            extra=intent.data_mapping,
        )
        answers: dict[str, Any] = {
            "data_file": WORK_INPUT_NAME,
            **self._answers_from_intent(intent),
            **mapping,
        }
        if intent.figure_type is IntentFigureType.VIOLIN:
            answers.setdefault("variant", "violin")

        from core.execution_manager import ExecutionManager
        from core.figure_engine import FigureEngine

        engine = FigureEngine(
            execution_manager=ExecutionManager(execute_fn=self.execute_fn),
        )
        result = engine.run(
            figure_id,
            answers=answers,
            available_columns=headers,
            user_request=user_prompt,
            work_dir=work,
            data_source=WORK_INPUT_NAME,
            execute=True,
        )
        if result.spec:
            (work / "spec.json").write_text(
                json.dumps(result.spec, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            history = SpecHistory.from_initial(
                result.spec,
                note="initial",
                r_code=_read_text_if_exists(Path(result.r_script_path)) if result.r_script_path else "",
            )
            self._save_history(work, history)
        else:
            history = None
        status: Literal["success", "failure", "need_information", "unmatched"]
        if result.status == "success":
            status = "success"
        elif result.status == "need_information":
            status = "need_information"
        else:
            status = "failure"
        return WorkflowResult(
            status=status,
            intent=intent_dump,
            spec=result.spec,
            history=history.summary() if history else None,
            previous_version=1 if history else 0,
            current_version=history.current_version if history else 0,
            r_script_path=result.r_script_path,
            output_files=result.output_files,
            qc_report=result.qc_report,
            questions=result.questions,
            missing_parameters=result.missing_fields,
            message=result.message,
            log=result.log,
        )

    def refine_figure(
        self,
        work_dir: str | Path,
        user_request: str,
        *,
        action: Literal["refine", "undo", "redo"] = "refine",
    ) -> WorkflowResult:
        """Apply NL design refinement (or undo/redo) then regenerate figure + QC."""
        work = Path(work_dir)
        if not (work / WORK_INPUT_NAME).is_file():
            return WorkflowResult(status="failure", message="No existing figure session")

        history = self._load_history(work)
        if history is None:
            spec_path = work / "spec.json"
            if not spec_path.is_file():
                return WorkflowResult(status="failure", message="No existing Figure Specification")
            history = SpecHistory.from_initial(
                json.loads(spec_path.read_text(encoding="utf-8")),
                note="initial",
                r_code=_read_text_if_exists(self._resolve_script_path(work)),
            )
            self._save_history(work, history)

        if action == "undo":
            entry = history.undo()
            if entry is None:
                return WorkflowResult(
                    status="failure",
                    message="Nothing to undo",
                    history=history.summary(),
                    current_version=history.current_version,
                    previous_version=history.current_version,
                    spec=history.current_spec(),
                )
            self._save_history(work, history)
            return self._render_refined(
                entry.spec,
                work,
                history=history,
                message="Undone to previous Spec version",
                r_code=entry.r_code or None,
            )

        if action == "redo":
            entry = history.redo()
            if entry is None:
                return WorkflowResult(
                    status="failure",
                    message="Nothing to redo",
                    history=history.summary(),
                    current_version=history.current_version,
                    previous_version=history.current_version,
                    spec=history.current_spec(),
                )
            self._save_history(work, history)
            return self._render_refined(
                entry.spec,
                work,
                history=history,
                message="Redone to next Spec version",
                r_code=entry.r_code or None,
            )

        current = history.current_spec()
        use_llm_edit = looks_like_science_transform(user_request)
        refined = None
        if not use_llm_edit:
            refined = self.refinement_agent.refine(current, user_request, history=history)
            if refined.status == "ready" and refined.updated_spec is not None:
                self._save_history(work, history)
                result = self._render_refined(
                    refined.updated_spec,
                    work,
                    history=history,
                    previous_spec=refined.previous_spec,
                    modifications=[m.model_dump(mode="json") for m in refined.modifications],
                    message=f"Figure refined ({refined.source})",
                )
                result.previous_version = refined.previous_version
                result.current_version = refined.current_version
                self._attach_r_code_to_current_history(work, history, result.r_script_path)
                result.history = history.summary()
                return result
            # Style refine unmatched → fall through to LLM R editor.

        return self._refine_via_llm_r_edit(
            work,
            history,
            user_request=user_request,
            current_spec=current,
            previous_style_message=(refined.message if refined is not None else ""),
        )

    def _refine_via_llm_r_edit(
        self,
        work: Path,
        history: SpecHistory,
        *,
        user_request: str,
        current_spec: dict[str, Any],
        previous_style_message: str = "",
    ) -> WorkflowResult:
        script_path = self._resolve_script_path(work, current_spec)
        current_r = history.current_r_code() or _read_text_if_exists(script_path)
        if not current_r.strip():
            return WorkflowResult(
                status="failure",
                spec=current_spec,
                history=history.summary(),
                previous_version=history.current_version,
                current_version=history.current_version,
                message="No R script available for LLM code edit",
            )

        headers = self._table_headers(work / WORK_INPUT_NAME)
        summary = {
            "figure_definition_id": current_spec.get("figure_definition_id"),
            "figure_type": current_spec.get("figure_type"),
            "data_mapping": current_spec.get("data_mapping"),
            "visual_parameters": current_spec.get("visual_parameters"),
            "style_profile": current_spec.get("style_profile"),
            "statistics": current_spec.get("statistics"),
        }
        try:
            new_r = self.r_code_editor.edit(
                user_request,
                current_r,
                spec_summary=summary,
                column_names=headers,
            )
        except LLMError as exc:
            detail = str(exc)
            if previous_style_message:
                detail = f"{previous_style_message}; LLM R edit failed: {detail}"
            return WorkflowResult(
                status="failure",
                spec=current_spec,
                history=history.summary(),
                previous_version=history.current_version,
                current_version=history.current_version,
                message=detail,
            )

        updated_spec = dict(current_spec)
        visual = dict(updated_spec.get("visual_parameters") or {})
        lowered = user_request.lower()
        if "log10" in lowered or "log 10" in lowered:
            visual["y_transform"] = "-log10"
        updated_spec["visual_parameters"] = visual

        previous_version = history.current_version
        history.push(
            updated_spec,
            modifications=[
                FigureModification(
                    target_parameter="r_code",
                    old_value=None,
                    new_value="llm_edit",
                    reason=user_request.strip(),
                    confidence=0.8,
                )
            ],
            note=user_request.strip(),
            r_code=new_r,
        )
        self._save_history(work, history)
        result = self._render_refined(
            updated_spec,
            work,
            history=history,
            previous_spec=current_spec,
            modifications=[{"target_parameter": "r_code", "reason": user_request.strip()}],
            message="Figure refined (llm_r_edit)",
            r_code=new_r,
        )
        result.previous_version = previous_version
        result.current_version = history.current_version
        return result

    def _render_refined(
        self,
        spec_dump: dict[str, Any],
        work: Path,
        *,
        history: SpecHistory | None = None,
        previous_spec: dict[str, Any] | None = None,
        modifications: list[dict[str, Any]] | None = None,
        message: str = "",
        intent_dump: dict[str, Any] | None = None,
        r_code: str | None = None,
    ) -> WorkflowResult:
        """Shared render after Refine / undo / redo.

        If r_code is provided, execute that script (LLM edits / undo restore).
        Otherwise regenerate R from Spec (style Refine).
        """
        if r_code:
            return self._execute_r_snapshot(
                spec_dump,
                work,
                r_code=r_code,
                history=history,
                previous_spec=previous_spec,
                modifications=modifications,
                message=message,
            )

        if spec_dump.get("figure_definition_id"):
            from core.execution_manager import ExecutionManager
            from core.figure_engine import FigureEngine

            engine = FigureEngine(
                execution_manager=ExecutionManager(execute_fn=self.execute_fn),
            )
            rendered = engine.render_from_spec(spec_dump, work, execute=True)
            (work / "spec.json").write_text(
                json.dumps(spec_dump, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            if history is not None:
                self._save_history(work, history)
            status: Literal["success", "failure", "need_information", "unmatched"]
            status = "success" if rendered.status == "success" else "failure"
            qc_status = (rendered.qc_report or {}).get("status", "pass")
            final_message = message
            if qc_status not in {"pass", None}:
                final_message = (message + " | QC warning").strip(" |") if message else "QC warning"
            return WorkflowResult(
                status=status,
                spec=rendered.spec or spec_dump,
                previous_spec=previous_spec,
                modifications=modifications or [],
                history=history.summary() if history else None,
                previous_version=max(1, history.current_version - 1) if history else 0,
                current_version=history.current_version if history else 1,
                r_script_path=rendered.r_script_path,
                output_files=rendered.output_files or _list_artifacts(work),
                qc_report=rendered.qc_report,
                message=final_message if status == "success" else rendered.message,
                log=rendered.log,
            )

        spec = FigureSpecification.model_validate(spec_dump)
        return self._render_and_qc(
            spec,
            work,
            intent_dump=intent_dump,
            history=history,
            previous_spec=previous_spec,
            modifications=modifications,
            message=message,
        )

    def _execute_r_snapshot(
        self,
        spec_dump: dict[str, Any],
        work: Path,
        *,
        r_code: str,
        history: SpecHistory | None = None,
        previous_spec: dict[str, Any] | None = None,
        modifications: list[dict[str, Any]] | None = None,
        message: str = "",
    ) -> WorkflowResult:
        script_path = self._resolve_script_path(work, spec_dump)
        script_path.write_text(r_code, encoding="utf-8")
        (work / "spec.json").write_text(
            json.dumps(spec_dump, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        execution = self.execute_fn(script_path, work)

        qc_dump: dict[str, Any]
        try:
            if spec_dump.get("figure_definition_id"):
                from core.qc_manager import QCManager

                qc_dump = QCManager().run_qc(spec_dump, work).model_dump(mode="json")
            else:
                qc_dump = self.qc_agent.check(
                    FigureSpecification.model_validate(spec_dump),
                    work,
                ).model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            qc_dump = {"status": "failed", "message": str(exc)}

        if history is not None:
            self._save_history(work, history)

        output_files = _list_artifacts(work)
        status: Literal["success", "failure", "need_information", "unmatched"]
        status = "success" if execution.status == "success" else "failure"
        final_message = message
        if status == "success" and qc_dump.get("status") not in {"pass", None}:
            final_message = (message + " | QC warning").strip(" |") if message else "QC warning"
        return WorkflowResult(
            status=status,
            spec=spec_dump,
            previous_spec=previous_spec,
            modifications=modifications or [],
            history=history.summary() if history else None,
            previous_version=max(1, history.current_version - 1) if history else 0,
            current_version=history.current_version if history else 1,
            r_script_path=str(script_path),
            output_files=output_files,
            qc_report=qc_dump,
            message=final_message if status == "success" else "Execution failed",
            log=execution.log,
        )

    def _attach_r_code_to_current_history(
        self,
        work: Path,
        history: SpecHistory,
        r_script_path: str,
    ) -> None:
        code = _read_text_if_exists(Path(r_script_path)) if r_script_path else ""
        if not code and history.versions:
            return
        if history.current_index >= 0 and history.versions:
            history.versions[history.current_index].r_code = code
            self._save_history(work, history)

    @staticmethod
    def _resolve_script_path(work: Path, spec: dict[str, Any] | None = None) -> Path:
        for name in ("figure.R", "volcano.R", "scatter.R", "boxplot.R"):
            path = work / name
            if path.is_file():
                return path
        if spec and spec.get("figure_definition_id"):
            return work / "figure.R"
        return work / WORK_SCRIPT_NAME

    def _render_and_qc(
        self,
        spec: FigureSpecification,
        work: Path,
        *,
        intent_dump: dict[str, Any] | None = None,
        history: SpecHistory | None = None,
        previous_spec: dict[str, Any] | None = None,
        modifications: list[dict[str, Any]] | None = None,
        message: str = "",
        init_history: bool = False,
    ) -> WorkflowResult:
        spec.plot.data.source = WORK_INPUT_NAME
        script_path = work / WORK_SCRIPT_NAME
        self.r_code_agent.generate(spec, output_path=script_path)

        execution = self.execute_fn(script_path, work)
        qc = self.qc_agent.check(spec, work)
        qc_dump = qc.model_dump(mode="json")
        spec_dump = spec.model_dump(mode="json", by_alias=True)
        (work / "spec.json").write_text(
            spec.model_dump_json(indent=2, by_alias=True),
            encoding="utf-8",
        )

        if init_history:
            history = SpecHistory.from_initial(
                spec,
                note="initial",
                r_code=_read_text_if_exists(script_path),
            )
            self._save_history(work, history)
        elif history is not None:
            self._save_history(work, history)

        history_summary = history.summary() if history else None
        current_version = history.current_version if history else 1
        previous_version = (
            max(1, current_version - 1) if modifications else current_version
        )
        if previous_spec is not None and history is not None:
            previous_version = max(1, current_version - 1)

        output_files = _list_artifacts(work)
        if execution.status != "success":
            return WorkflowResult(
                status="failure",
                intent=intent_dump,
                spec=spec_dump,
                previous_spec=previous_spec,
                modifications=modifications or [],
                history=history_summary,
                previous_version=previous_version,
                current_version=current_version,
                r_script_path=str(script_path),
                output_files=output_files,
                qc_report=qc_dump,
                message="Execution failed",
                log=execution.log,
            )

        final_message = message
        if qc.status.value != "pass":
            final_message = (message + " | QC warning").strip(" |") if message else "QC warning"

        return WorkflowResult(
            status="success",
            intent=intent_dump,
            spec=spec_dump,
            previous_spec=previous_spec,
            modifications=modifications or [],
            history=history_summary,
            previous_version=previous_version,
            current_version=current_version,
            r_script_path=str(script_path),
            output_files=output_files,
            qc_report=qc_dump,
            message=final_message,
            log=execution.log,
        )

    @staticmethod
    def _answers_from_intent(intent: FigureIntent) -> dict[str, Any]:
        purpose = "publication" if intent.purpose is IntentPurpose.PUBLICATION else "internal"
        answers: dict[str, Any] = {"purpose": purpose}
        if intent.journal_style.value != "Custom":
            answers["journal_style"] = intent.journal_style.value
        return answers

    def _prepare_input(self, source: Path, dest: Path) -> WorkflowResult | None:
        if not source.is_file():
            return WorkflowResult(status="failure", message="Invalid input file")
        if source.suffix.lower() not in ALLOWED_SUFFIXES:
            return WorkflowResult(status="failure", message="Invalid input file")
        try:
            delimiter = "\t" if source.suffix.lower() == ".tsv" else ","
            with source.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle, delimiter=delimiter))
        except (OSError, UnicodeError, csv.Error):
            return WorkflowResult(status="failure", message="Invalid input file")

        if not rows or len(rows[0]) < 2 or not any(cell.strip() for cell in rows[0]):
            return WorkflowResult(status="failure", message="Invalid input file")

        with dest.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows(rows)
        return None

    @staticmethod
    def _table_headers(table: Path) -> list[str]:
        with table.open("r", encoding="utf-8-sig", newline="") as handle:
            headers = next(csv.reader(handle))
        return [name.strip() for name in headers if name.strip()]

    def _answers_from_table(self, table: Path) -> dict[str, Any]:
        with table.open("r", encoding="utf-8-sig", newline="") as handle:
            headers = next(csv.reader(handle))
        lookup = {name.strip().lower(): name.strip() for name in headers if name.strip()}
        answers: dict[str, Any] = {"data_file": WORK_INPUT_NAME}
        questions = {
            item["id"]: item for item in self.requirement_agent.rules.get("user_questions", [])
        }
        for param_id in ("gene_column", "log2FC_column", "pvalue_column"):
            question = questions.get(param_id, {})
            for candidate in question.get("common_names", []):
                hit = lookup.get(str(candidate).lower())
                if hit:
                    answers[param_id] = hit
                    break
        sig_col = answers.get("pvalue_column", "")
        lowered = str(sig_col).lower()
        if lowered in {"padj", "fdr", "qvalue", "q_value"}:
            answers["significance_metric"] = "FDR"
        elif lowered:
            answers["significance_metric"] = "p-value"
        return answers

    @staticmethod
    def _load_history(work: Path) -> SpecHistory | None:
        path = work / HISTORY_NAME
        if not path.is_file():
            return None
        return SpecHistory.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _save_history(work: Path, history: SpecHistory) -> None:
        (work / HISTORY_NAME).write_text(
            history.model_dump_json(indent=2),
            encoding="utf-8",
        )


def _read_text_if_exists(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _list_artifacts(work: Path) -> list[str]:
    names = []
    for path in sorted(work.iterdir(), key=lambda item: item.name.lower()):
        if path.is_file() and path.name != "input.csv":
            names.append(path.name)
    return names

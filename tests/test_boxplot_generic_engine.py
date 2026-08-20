"""Second-figure validation: basic_statistics.boxplot via Generic Figure Engine."""

from __future__ import annotations

from pathlib import Path

from core.code_generation_engine import CodeGenerationEngine
from core.execution_manager import ExecutionManager
from core.figure_engine import FigureEngine
from core.figure_registry import FigureRegistry
from core.requirement_engine import GenericRequirementStatus, RequirementEngine
from core.specification_builder import SpecificationBuilder
from core.strategies.boxplot_strategy import BoxplotStrategy
from schemas.figure_definition import FigureDefinition
from services.r_executor import ExecutionResult

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example_boxplot.csv"


def _stub_execute(script_path, output_dir, **kwargs) -> ExecutionResult:
    out = Path(output_dir)
    (out / "boxplot.pdf").write_bytes(b"%PDF-1.4\n")
    (out / "boxplot.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (out / "boxplot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return ExecutionResult(
        status="success",
        output_files=["boxplot.pdf", "boxplot.svg", "boxplot.png"],
        log="stub-ok",
    )


def test_case1_generic_engine_generates_boxplot_r(tmp_path: Path) -> None:
    engine = FigureEngine(execution_manager=ExecutionManager(execute_fn=_stub_execute))
    result = engine.run(
        "basic_statistics.boxplot",
        answers={
            "group": "group",
            "value": "value",
            "data_file": "input.csv",
            "point_size": 1.5,
        },
        available_columns=["group", "value", "sample_id"],
        work_dir=tmp_path,
        data_source="input.csv",
        execute=True,
    )
    assert result.status == "success"
    assert result.figure_definition_id == "basic_statistics.boxplot"
    code = Path(result.r_script_path).read_text(encoding="utf-8")
    assert "library(ggplot2)" in code
    assert "geom_boxplot" in code
    assert "theme_classic" in code
    assert result.spec is not None
    assert result.spec["data_mapping"]["group"] == "group"
    assert result.spec["data_mapping"]["value"] == "value"
    assert result.qc_report is not None


def test_case2_missing_value_field() -> None:
    registry = FigureRegistry()
    definition = registry.get_figure_definition("basic_statistics.boxplot")
    response = RequirementEngine().collect(
        definition,
        answers={"group": "group"},
        available_columns=["group"],
    )
    assert response.status is GenericRequirementStatus.NEED_INFORMATION
    assert "value" in response.missing_fields
    assert "group" not in response.missing_fields


def test_case3_requirement_follows_definition_not_boxplot_hardcoding() -> None:
    registry = FigureRegistry()
    definition = registry.get_figure_definition("basic_statistics.boxplot")
    mutated = FigureDefinition.model_validate(
        {
            **definition.model_dump(mode="json"),
            "required_fields": [
                {"role": "group", "type": "categorical"},
                {"role": "batch", "type": "categorical"},
            ],
        }
    )
    response = RequirementEngine().collect(
        mutated,
        answers={"group": "group"},
        available_columns=["group"],
    )
    assert response.status is GenericRequirementStatus.NEED_INFORMATION
    assert response.missing_fields == ["batch"]
    assert "value" not in response.missing_fields


def test_case4_point_size_changes_r_code() -> None:
    registry = FigureRegistry()
    definition = registry.get_figure_definition("basic_statistics.boxplot")
    base_answers = {
        "group": "group",
        "value": "value",
        "data_file": "input.csv",
        "point_size": 1.0,
    }
    req_a = RequirementEngine().collect(
        definition,
        answers=base_answers,
        available_columns=["group", "value"],
    )
    req_b = RequirementEngine().collect(
        definition,
        answers={**base_answers, "point_size": 3.5},
        available_columns=["group", "value"],
    )
    assert req_a.status is GenericRequirementStatus.READY
    assert req_b.status is GenericRequirementStatus.READY
    spec_a = SpecificationBuilder().build(definition, req_a, data_source="input.csv")
    spec_b = SpecificationBuilder().build(definition, req_b, data_source="input.csv")
    code_a = CodeGenerationEngine([BoxplotStrategy()]).generate(spec_a)
    code_b = CodeGenerationEngine([BoxplotStrategy()]).generate(spec_b)
    assert "point_size <- 1.0" in code_a or "point_size <- 1" in code_a
    assert "point_size <- 3.5" in code_b
    assert code_a != code_b


def test_case5_catalog_only_still_rejected() -> None:
    engine = FigureEngine()
    result = engine.run("transcriptomics.DEG_heatmap", answers={})
    assert result.status == "unavailable"
    assert "implementation unavailable" in result.message


def test_boxplot_is_executable_in_registry() -> None:
    registry = FigureRegistry()
    meta = registry.get_metadata("basic_statistics.boxplot")
    assert meta.is_executable
    assert meta.implementation_status.value == "execution_verified"
    assert registry.get_figure_definition("basic_statistics.boxplot").data_schema_id == "group_numeric_table"


def test_example_csv_exists() -> None:
    assert EXAMPLE.is_file()
    text = EXAMPLE.read_text(encoding="utf-8")
    assert "group" in text.splitlines()[0]
    assert "value" in text.splitlines()[0]

"""Generic Figure Engine tests."""

from __future__ import annotations

from pathlib import Path

from core.code_generation_engine import CodeGenerationEngine
from core.execution_manager import ExecutionManager
from core.figure_engine import FigureEngine
from core.figure_registry import FigureRegistry
from core.requirement_engine import GenericRequirementStatus, RequirementEngine
from core.specification_builder import SpecificationBuilder
from core.strategies.volcano_strategy import VolcanoStrategy
from schemas.figure_definition import FigureDefinition
from schemas.generic_figure_spec import GenericFigureSpecification
from services.r_executor import ExecutionResult


def _stub_execute(script_path, output_dir, **kwargs) -> ExecutionResult:
    out = Path(output_dir)
    (out / "volcano.pdf").write_bytes(b"%PDF-1.4\n")
    (out / "volcano.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (out / "volcano.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return ExecutionResult(
        status="success",
        output_files=["volcano.pdf", "volcano.svg", "volcano.png"],
        log="stub-ok",
    )


def test_case1_generic_engine_runs_volcano(tmp_path: Path) -> None:
    engine = FigureEngine(execution_manager=ExecutionManager(execute_fn=_stub_execute))
    result = engine.run(
        "transcriptomics.volcano",
        answers={
            "feature_id": "gene",
            "effect_size": "log2FoldChange",
            "significance": "padj",
            "data_file": "input.csv",
            "journal_style": "Nature",
        },
        available_columns=["gene", "log2FoldChange", "padj", "pvalue"],
        work_dir=tmp_path,
        data_source="input.csv",
        execute=True,
    )
    assert result.status == "success"
    assert result.figure_definition_id == "transcriptomics.volcano"
    assert Path(result.r_script_path).is_file()
    assert "ggplot" in Path(result.r_script_path).read_text(encoding="utf-8")
    assert result.spec is not None
    assert result.spec["figure_definition_id"] == "transcriptomics.volcano"
    assert result.spec["data_mapping"]["feature_id"] == "gene"


def test_case2_requirement_engine_missing_fields_from_definition() -> None:
    registry = FigureRegistry()
    definition = registry.get_figure_definition("transcriptomics.volcano")
    response = RequirementEngine().collect(definition, answers={}, available_columns=[])
    assert response.status is GenericRequirementStatus.NEED_INFORMATION
    assert set(response.missing_fields) == {"feature_id", "effect_size", "significance"}
    assert len(response.questions) == 3


def test_case3_requirement_follows_definition_not_hardcoded_volcano() -> None:
    """Mutating required_fields must change missing fields — no figure-type if-branch."""
    registry = FigureRegistry()
    definition = registry.get_figure_definition("transcriptomics.volcano")
    mutated = FigureDefinition.model_validate(
        {
            **definition.model_dump(mode="json"),
            "required_fields": [
                {"role": "feature_id", "type": "string"},
                {"role": "custom_score", "type": "numeric"},
            ],
        }
    )
    response = RequirementEngine().collect(
        mutated,
        answers={"feature_id": "gene"},
        available_columns=["gene"],
    )
    assert response.status is GenericRequirementStatus.NEED_INFORMATION
    assert response.missing_fields == ["custom_score"]
    assert "effect_size" not in response.missing_fields
    assert "significance" not in response.missing_fields


def test_case4_catalog_only_figure_rejected() -> None:
    engine = FigureEngine()
    result = engine.run("transcriptomics.DEG_heatmap", answers={})
    assert result.status == "unavailable"
    assert "implementation unavailable" in result.message.lower() or "cataloged but implementation unavailable" in result.message


def test_case5_unknown_figure_id() -> None:
    engine = FigureEngine()
    result = engine.run("does_not.exist_figure")
    assert result.status == "unknown_figure"
    assert "Unknown figure_id" in result.message


def test_registry_lists_all_catalog_families() -> None:
    registry = FigureRegistry()
    metas = registry.list_available_figures()
    assert len(metas) >= 86
    assert registry.get_metadata("transcriptomics.volcano").is_executable
    assert not registry.get_metadata("clinical.Kaplan_Meier").is_executable


def test_specification_builder_and_volcano_strategy(tmp_path: Path) -> None:
    registry = FigureRegistry()
    definition = registry.get_figure_definition("transcriptomics.volcano")
    req = RequirementEngine().collect(
        definition,
        answers={
            "feature_id": "gene",
            "effect_size": "log2FoldChange",
            "significance": "padj",
            "data_file": "input.csv",
        },
        available_columns=["gene", "log2FoldChange", "padj"],
    )
    assert req.status is GenericRequirementStatus.READY
    spec = SpecificationBuilder().build(definition, req, data_source="input.csv")
    assert isinstance(spec, GenericFigureSpecification)
    code = CodeGenerationEngine([VolcanoStrategy()]).generate(spec, output_path=tmp_path / "figure.R")
    assert "geom_point" in code
    assert 'gene_col <- "gene"' in code

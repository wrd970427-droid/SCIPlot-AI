"""Scatter via Generic Engine + Web workflow routing."""

from __future__ import annotations

from pathlib import Path

from core.column_mapper import map_columns_from_request
from core.execution_manager import ExecutionManager
from core.figure_engine import FigureEngine
from llm.intent_parser import IntentParser
from schemas.figure_intent import IntentFigureType
from services.r_executor import ExecutionResult
from services.workflow import FigureWorkflow

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example_scatter.csv"


def _stub_execute(script_path, output_dir, **kwargs) -> ExecutionResult:
    out = Path(output_dir)
    (out / "scatter.pdf").write_bytes(b"%PDF-1.4\n")
    (out / "scatter.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (out / "scatter.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return ExecutionResult(
        status="success",
        output_files=["scatter.pdf", "scatter.svg", "scatter.png"],
        log="stub-ok",
    )


def test_column_mapper_matches_pipe_headers() -> None:
    columns = ["gene", "neg|lfc", "neg|p-value", "neg|goodsgrna"]
    mapping = map_columns_from_request(
        "绘制散点图，neg|p-value为Y轴，neg|lfc为X轴，neg|goodsgrna为点的大小",
        columns,
    )
    assert mapping["x"] == "neg|lfc"
    assert mapping["y"] == "neg|p-value"
    assert mapping["size"] == "neg|goodsgrna"


def test_generic_engine_scatter_from_prompt(tmp_path: Path) -> None:
    engine = FigureEngine(execution_manager=ExecutionManager(execute_fn=_stub_execute))
    result = engine.run(
        "basic_statistics.scatter",
        answers={"data_file": "input.csv"},
        available_columns=["gene", "neg|lfc", "neg|p-value", "neg|goodsgrna"],
        user_request="绘制散点图，neg|p-value为Y轴，neg|lfc为X轴，neg|goodsgrna为点的大小",
        work_dir=tmp_path,
        data_source="input.csv",
        execute=True,
    )
    assert result.status == "success"
    code = Path(result.r_script_path).read_text(encoding="utf-8")
    assert "geom_point" in code
    assert 'x_col <- "neg|lfc"' in code
    assert 'y_col <- "neg|p-value"' in code
    assert 'size_col <- "neg|goodsgrna"' in code
    assert "scale_size_area" in code


def test_workflow_scatter_no_longer_unsupported(tmp_path: Path) -> None:
    workflow = FigureWorkflow(execute_fn=_stub_execute, intent_parser=IntentParser(enabled=False))
    result = workflow.generate_figure(
        "绘制散点图，neg|p-value为Y轴，neg|lfc为X轴，neg|goodsgrna为点的大小",
        EXAMPLE,
        work_dir=tmp_path,
    )
    assert result.status == "success"
    assert result.intent is not None
    assert result.intent["figure_type"] == IntentFigureType.SCATTER.value
    assert result.spec is not None
    assert result.spec["figure_definition_id"] == "basic_statistics.scatter"
    assert result.spec["data_mapping"]["x"] == "neg|lfc"
    assert result.spec["data_mapping"]["size"] == "neg|goodsgrna"
    assert Path(result.r_script_path).is_file()
    assert "ggplot" in Path(result.r_script_path).read_text(encoding="utf-8")


def test_refine_scatter_point_smaller_shrinks_size_max(tmp_path: Path) -> None:
    workflow = FigureWorkflow(execute_fn=_stub_execute, intent_parser=IntentParser(enabled=False))
    generated = workflow.generate_figure(
        "绘制散点图，neg|p-value为Y轴，neg|lfc为X轴，neg|goodsgrna为点的大小",
        EXAMPLE,
        work_dir=tmp_path,
    )
    assert generated.status == "success"
    before_max = float((generated.spec.get("visual_parameters") or {}).get("size_max", 6))
    refined = workflow.refine_figure(tmp_path, "点的大小，小一点")
    assert refined.status == "success"
    assert refined.spec is not None
    after_max = float(refined.spec["visual_parameters"]["size_max"])
    assert after_max < before_max
    code = Path(refined.r_script_path).read_text(encoding="utf-8")
    assert f"size_max <- {after_max}" in code or f"size_max <- {after_max:g}" in code
    assert "scale_size_area(max_size = size_max)" in code


def test_refine_scatter_point_color_blue_updates_r(tmp_path: Path) -> None:
    workflow = FigureWorkflow(execute_fn=_stub_execute, intent_parser=IntentParser(enabled=False))
    generated = workflow.generate_figure(
        "绘制散点图，neg|p-value为Y轴，neg|lfc为X轴，neg|goodsgrna为点的大小",
        EXAMPLE,
        work_dir=tmp_path,
    )
    assert generated.status == "success"
    refined = workflow.refine_figure(tmp_path, "点的颜色修改为蓝色")
    assert refined.status == "success"
    assert refined.spec is not None
    assert refined.spec["visual_parameters"]["point_color"] == "#2E86AB"
    code = Path(refined.r_script_path).read_text(encoding="utf-8")
    assert 'point_color <- "#2E86AB"' in code
    assert "color = point_color" in code


def test_refine_scatter_uses_shared_refinement_path(tmp_path: Path) -> None:
    workflow = FigureWorkflow(execute_fn=_stub_execute, intent_parser=IntentParser(enabled=False))
    generated = workflow.generate_figure(
        "绘制散点图，neg|p-value为Y轴，neg|lfc为X轴，neg|goodsgrna为点的大小",
        EXAMPLE,
        work_dir=tmp_path,
    )
    assert generated.status == "success"
    before = generated.spec["visual_parameters"]["font_size"]
    refined = workflow.refine_figure(tmp_path, "字体大一点")
    assert refined.status == "success"
    assert refined.spec is not None
    assert refined.spec["figure_definition_id"] == "basic_statistics.scatter"
    assert refined.spec["visual_parameters"]["font_size"] == before + 2
    assert refined.spec["data_mapping"]["x"] == "neg|lfc"
    assert refined.current_version == 2
    code = Path(refined.r_script_path).read_text(encoding="utf-8")
    assert f"font_size <- {before + 2}" in code or f"font_size <- {float(before) + 2}" in code

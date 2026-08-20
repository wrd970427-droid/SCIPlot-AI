"""End-to-end FigureWorkflow tests. Does not require Docker."""

from __future__ import annotations

from pathlib import Path

from llm.intent_parser import IntentParser
from services.r_executor import ExecutionResult
from services.workflow import FigureWorkflow

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example_volcano.csv"


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


def test_case1_nature_volcano_workflow_succeeds(tmp_path: Path) -> None:
    workflow = FigureWorkflow(execute_fn=_stub_execute, intent_parser=IntentParser(enabled=False))
    result = workflow.generate_figure(
        "帮我生成Nature风格火山图",
        EXAMPLE,
        work_dir=tmp_path,
    )
    assert result.status == "success"
    assert result.spec is not None
    assert result.spec["figure_type"] == "volcano"
    assert result.spec["journal_style"] == "Nature"
    assert Path(result.r_script_path).is_file()
    assert "ggplot" in Path(result.r_script_path).read_text(encoding="utf-8")
    assert result.qc_report is not None
    assert result.qc_report["status"] in {"pass", "warning"}
    assert "volcano.R" in result.output_files
    assert "QC_report.json" in result.output_files


def test_case2_invalid_csv_fails(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("this is not a table\n", encoding="utf-8")
    workflow = FigureWorkflow(execute_fn=_stub_execute, intent_parser=IntentParser(enabled=False))
    result = workflow.generate_figure("帮我生成Nature风格火山图", bad, work_dir=tmp_path / "work")
    assert result.status == "failure"
    assert result.message == "Invalid input file"


def test_case3_missing_parameters_need_information(tmp_path: Path) -> None:
    table = tmp_path / "unknown.csv"
    table.write_text("foo,bar,baz\n1,2,3\n", encoding="utf-8")
    workflow = FigureWorkflow(execute_fn=_stub_execute, intent_parser=IntentParser(enabled=False))
    result = workflow.generate_figure(
        "帮我生成Nature风格火山图",
        table,
        work_dir=tmp_path / "work",
    )
    assert result.status == "need_information"
    assert result.message == "Required information missing"
    assert result.missing_parameters
    assert result.questions
    assert result.intent is not None
    assert result.intent["figure_type"] == "volcano"
    assert result.intent["source"] == "fallback"


def test_intent_parser_fallback_keeps_workflow_runnable(tmp_path: Path) -> None:
    workflow = FigureWorkflow(execute_fn=_stub_execute, intent_parser=IntentParser(enabled=False))
    result = workflow.generate_figure(
        "我有RNA-seq差异分析结果，想做Nature风格火山图",
        EXAMPLE,
        work_dir=tmp_path,
    )
    assert result.status == "success"
    assert result.intent is not None
    assert result.intent["source"] == "fallback"
    assert result.intent["figure_type"] == "volcano"
    assert (tmp_path / "intent.json").is_file()

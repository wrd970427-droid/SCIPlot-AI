"""LLM R code editor + Refine science-transform fallback (Fake LLM, no Docker)."""

from __future__ import annotations

import json
from pathlib import Path

from llm.intent_parser import IntentParser
from llm.llm_client import LLMError
from llm.r_code_editor import RCodeEditor, looks_like_science_transform
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


class _FakeLLM:
    def __init__(self, content: str = "", *, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.available = True
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]], **kwargs) -> str:
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.content


def _edited_r_with_log10(base: str) -> str:
    # Minimal transform: force y aesthetic to -log10 of y column.
    if "aes(x = .data[[x_col]], y = .data[[y_col]]" in base:
        return base.replace(
            "aes(x = .data[[x_col]], y = .data[[y_col]]",
            "aes(x = .data[[x_col]], y = -log10(.data[[y_col]])",
            1,
        )
    return base + "\n# -log10 transform applied\np <- p + labs(y = '-log10(y)')\n"


def test_looks_like_science_transform() -> None:
    assert looks_like_science_transform("纵轴改成 -log10(neg|p-value)")
    assert looks_like_science_transform("y axis log2")
    assert not looks_like_science_transform("字体大一点")
    assert not looks_like_science_transform("点的颜色修改为蓝色")


def test_r_code_editor_edit_returns_full_script() -> None:
    current = "library(ggplot2)\np <- ggplot(df, aes(x, y)) + geom_point()\nggsave('out.pdf')\n"
    payload = json.dumps(
        {
            "r_code": current.replace("aes(x, y)", "aes(x, y = -log10(y))"),
            "summary": "y to -log10",
        }
    )
    fake = _FakeLLM(content=payload)
    editor = RCodeEditor(client=fake, enabled=True)
    out = editor.edit(
        "纵轴改成 -log10",
        current,
        spec_summary={"figure_definition_id": "basic_statistics.scatter"},
        column_names=["neg|lfc", "neg|p-value"],
    )
    assert "-log10" in out
    assert "ggplot" in out
    user_msg = fake.calls[0][1]["content"]
    assert "neg|p-value" in user_msg
    assert "1.23" not in user_msg
    assert "raw_data" not in user_msg


def test_case_a_science_refine_uses_llm_r_editor(tmp_path: Path) -> None:
    workflow = FigureWorkflow(execute_fn=_stub_execute, intent_parser=IntentParser(enabled=False))
    generated = workflow.generate_figure(
        "绘制散点图，neg|p-value为Y轴，neg|lfc为X轴，neg|goodsgrna为点的大小",
        EXAMPLE,
        work_dir=tmp_path,
    )
    assert generated.status == "success"
    assert generated.current_version == 1
    base_r = Path(generated.r_script_path).read_text(encoding="utf-8")
    assert "-log10" not in base_r or "aes(y = -log10" not in base_r

    edited = _edited_r_with_log10(base_r)
    fake = _FakeLLM(content=json.dumps({"r_code": edited, "summary": "y=-log10"}))
    workflow.r_code_editor = RCodeEditor(client=fake, enabled=True)

    refined = workflow.refine_figure(tmp_path, "纵轴改成 -log10(neg|p-value)")
    assert refined.status == "success"
    assert refined.current_version == 2
    assert refined.message.startswith("Figure refined (llm_r_edit)")
    code = Path(refined.r_script_path).read_text(encoding="utf-8")
    assert "-log10" in code
    assert refined.spec is not None
    assert refined.spec["visual_parameters"].get("y_transform") == "-log10"
    assert fake.calls, "LLM R editor should be invoked"
    prompt_blob = "\n".join(m["content"] for m in fake.calls[0])
    sample_csv = EXAMPLE.read_text(encoding="utf-8")
    first_data_line = sample_csv.strip().splitlines()[1]
    assert first_data_line not in prompt_blob
    assert "neg|p-value" in prompt_blob


def test_case_b_font_refine_skips_llm_editor(tmp_path: Path) -> None:
    fake = _FakeLLM(content='{"r_code":"should_not_run","summary":"x"}')
    workflow = FigureWorkflow(
        execute_fn=_stub_execute,
        intent_parser=IntentParser(enabled=False),
        r_code_editor=RCodeEditor(client=fake, enabled=True),
    )
    generated = workflow.generate_figure(
        "绘制散点图，neg|p-value为Y轴，neg|lfc为X轴，neg|goodsgrna为点的大小",
        EXAMPLE,
        work_dir=tmp_path,
    )
    assert generated.status == "success"
    before = generated.spec["visual_parameters"]["font_size"]
    refined = workflow.refine_figure(tmp_path, "字体大一点")
    assert refined.status == "success"
    assert refined.current_version == 2
    assert refined.spec["visual_parameters"]["font_size"] == before + 2
    assert "llm_r_edit" not in refined.message
    assert not fake.calls


def test_case_c_llm_unavailable_returns_clear_failure(tmp_path: Path) -> None:
    workflow = FigureWorkflow(
        execute_fn=_stub_execute,
        intent_parser=IntentParser(enabled=False),
        r_code_editor=RCodeEditor(client=_FakeLLM(error=LLMError("API_KEY missing")), enabled=False),
    )
    generated = workflow.generate_figure(
        "绘制散点图，neg|p-value为Y轴，neg|lfc为X轴",
        EXAMPLE,
        work_dir=tmp_path,
    )
    assert generated.status == "success"
    refined = workflow.refine_figure(tmp_path, "纵轴改成 -log10(neg|p-value)")
    assert refined.status == "failure"
    assert refined.current_version == 1
    assert "LLM" in refined.message or "unavailable" in refined.message.lower()


def test_undo_restores_r_code_snapshot(tmp_path: Path) -> None:
    workflow = FigureWorkflow(execute_fn=_stub_execute, intent_parser=IntentParser(enabled=False))
    generated = workflow.generate_figure(
        "绘制散点图，neg|p-value为Y轴，neg|lfc为X轴",
        EXAMPLE,
        work_dir=tmp_path,
    )
    base_r = Path(generated.r_script_path).read_text(encoding="utf-8")
    edited = _edited_r_with_log10(base_r)
    fake = _FakeLLM(content=json.dumps({"r_code": edited, "summary": "y=-log10"}))
    workflow.r_code_editor = RCodeEditor(client=fake, enabled=True)

    refined = workflow.refine_figure(tmp_path, "纵轴改成 -log10(neg|p-value)")
    assert refined.status == "success"
    assert "-log10" in Path(refined.r_script_path).read_text(encoding="utf-8")

    undone = workflow.refine_figure(tmp_path, "", action="undo")
    assert undone.status == "success"
    assert undone.current_version == 1
    restored = Path(undone.r_script_path).read_text(encoding="utf-8")
    assert restored == base_r or "-log10(.data[[y_col]])" not in restored

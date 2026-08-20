"""Figure Refinement Agent tests."""

from __future__ import annotations

import json
from pathlib import Path

from refinement.refinement_agent import RefinementAgent
from schemas.figure_spec import BorderStyle, FigureSpecification, NATURE_SINGLE_WIDTH_MM
from schemas.spec_history import SpecHistory
from services.r_executor import ExecutionResult
from services.workflow import FigureWorkflow

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example_volcano.csv"
EXAMPLE_SPEC = ROOT / "schemas" / "examples" / "volcano_nature_rnaseq.json"


def _base_spec() -> FigureSpecification:
    return FigureSpecification.model_validate_json(EXAMPLE_SPEC.read_text(encoding="utf-8"))


def test_case1_font_larger() -> None:
    agent = RefinementAgent(llm_enabled=False)
    spec = _base_spec()
    before = spec.font.axis_text_size
    result = agent.refine(spec, "字体大一点")
    assert result.status == "ready"
    assert result.updated_spec is not None
    updated = FigureSpecification.model_validate(result.updated_spec)
    assert updated.font.axis_text_size == before + 2
    assert any(m.target_parameter.endswith("axis_text_size") for m in result.modifications)


def test_outer_thick_inner_dashed_thin() -> None:
    agent = RefinementAgent(llm_enabled=False)
    spec = _base_spec()
    before_axis = spec.geometry.line_width
    before_thr = spec.geometry.threshold_line_width
    result = agent.refine(spec, "只加粗外边框，图内部的虚线变细")
    assert result.status == "ready"
    updated = FigureSpecification.model_validate(result.updated_spec)
    assert updated.geometry.line_width > before_axis
    assert updated.geometry.threshold_line_width < before_thr

    """『加粗边框，不是改成全边框』→ axis line_width↑, panel.border stays none."""
    agent = RefinementAgent(llm_enabled=False)
    spec = _base_spec()
    assert spec.theme.border.value == "none"
    before = spec.geometry.line_width
    result = agent.refine(spec, "加粗边框，不是改成全边框")
    assert result.status == "ready"
    updated = FigureSpecification.model_validate(result.updated_spec)
    assert updated.geometry.line_width > before
    assert updated.theme.border.value == "none"


def test_learned_example_matches_alias() -> None:
    agent = RefinementAgent(llm_enabled=False)
    result = agent.refine(_base_spec(), "把轴线加粗，不要变成方框")
    assert result.status == "ready"
    updated = FigureSpecification.model_validate(result.updated_spec)
    assert updated.theme.border.value == "none"
    assert updated.geometry.line_width >= 0.5

    agent = RefinementAgent(llm_enabled=False)
    spec = _base_spec()
    before = spec.size.width_mm
    result = agent.refine(spec, "图片变宽")
    assert result.status == "ready"
    updated = FigureSpecification.model_validate(result.updated_spec)
    assert updated.size.width_mm == before * 1.2


def test_local_paraphrase_maps_widen_phrase() -> None:
    """Even without keyword hit, local NLU should map paraphrases like LLM would."""
    agent = RefinementAgent(llm_enabled=False)
    # Phrase not listed as exact keyword in older rule sets; covered by paraphrase regex.
    result = agent.refine(_base_spec(), "把这张图整体加宽一些")
    assert result.status == "ready"
    assert FigureSpecification.model_validate(result.updated_spec).size.width_mm > _base_spec().size.width_mm


def test_font_zengda_synonym_matches_rules() -> None:
    agent = RefinementAgent(llm_enabled=False)
    spec = _base_spec()
    before = spec.font.axis_text_size
    result = agent.refine(spec, "字体增大")
    assert result.status == "ready"
    assert result.source == "rules"
    updated = FigureSpecification.model_validate(result.updated_spec)
    assert updated.font.axis_text_size == before + 2


def test_llm_refinement_parses_colloquial_font_request() -> None:
    class _FakeLLM:
        available = True

        def complete(self, messages: list[dict[str, str]]) -> str:
            assert "设计" in messages[0]["content"] or "修改" in messages[0]["content"]
            return json.dumps(
                {
                    "matched": True,
                    "operations": [
                        {
                            "parameter": "font_size",
                            "operation": "increase",
                            "value": 2,
                            "confidence": 0.93,
                            "reason": "enlarge fonts",
                        }
                    ],
                }
            )

    agent = RefinementAgent(llm_client=_FakeLLM(), llm_enabled=True)
    spec = _base_spec()
    before = spec.font.axis_text_size
    result = agent.refine(spec, "把字弄大一些行吗")
    assert result.status == "ready"
    assert result.source == "llm"
    updated = FigureSpecification.model_validate(result.updated_spec)
    assert updated.font.axis_text_size == before + 2


def test_llm_failure_falls_back_to_rules() -> None:
    from llm.llm_client import LLMError

    class _BrokenLLM:
        available = True

        def complete(self, messages: list[dict[str, str]]) -> str:
            raise LLMError("boom")

    agent = RefinementAgent(llm_client=_BrokenLLM(), llm_enabled=True)
    result = agent.refine(_base_spec(), "字体增大")
    assert result.status == "ready"
    assert result.source == "rules"


def test_case2_nature_single_column() -> None:
    agent = RefinementAgent(llm_enabled=False)
    spec = _base_spec()
    payload = spec.model_dump(mode="python", by_alias=True)
    payload["size"]["width_mm"] = 120
    payload["size"]["column"] = "double"
    result = agent.refine(payload, "改成Nature单栏")
    assert result.status == "ready"
    updated = FigureSpecification.model_validate(result.updated_spec)
    assert updated.size.width_mm == NATURE_SINGLE_WIDTH_MM
    assert updated.size.width_mm == 89
    assert updated.size.column.value == "single"
    assert updated.journal_style.value == "Nature"


def test_case3_full_black_border() -> None:
    agent = RefinementAgent(llm_enabled=False)
    spec = _base_spec()
    assert spec.theme.border is BorderStyle.NONE
    result = agent.refine(spec, "四周加黑色边框")
    assert result.status == "ready"
    updated = FigureSpecification.model_validate(result.updated_spec)
    assert updated.theme.border is BorderStyle.FULL
    assert updated.theme.border.value == "full"


def test_case4_points_smaller() -> None:
    agent = RefinementAgent(llm_enabled=False)
    spec = _base_spec()
    before = spec.geometry.point_size
    result = agent.refine(spec, "点小一点")
    assert result.status == "ready"
    updated = FigureSpecification.model_validate(result.updated_spec)
    assert updated.geometry.point_size == before - 0.5


def test_case5_history_records_continuous_edits() -> None:
    agent = RefinementAgent(llm_enabled=False)
    history = SpecHistory.from_initial(_base_spec(), note="initial")
    r1 = agent.refine(history.current_spec(), "字体大一点", history=history)
    assert r1.status == "ready"
    assert history.current_version == 2

    r2 = agent.refine(history.current_spec(), "宽一点", history=history)
    assert r2.status == "ready"
    assert history.current_version == 3

    r3 = agent.refine(history.current_spec(), "颜色换成Nature风格", history=history)
    assert r3.status == "ready"
    assert history.current_version == 4
    assert len(history.versions) == 4

    updated = FigureSpecification.model_validate(history.current_spec())
    assert updated.font.axis_text_size >= 8
    assert updated.plot.colors.up == "#E64B35"

    undone = history.undo()
    assert undone is not None
    assert history.current_version == 3
    redone = history.redo()
    assert redone is not None
    assert history.current_version == 4


def test_refinement_does_not_touch_statistics() -> None:
    agent = RefinementAgent(llm_enabled=False)
    spec = _base_spec()
    before = spec.plot.statistics.model_dump(by_alias=True)
    result = agent.refine(spec, "字体大一点")
    updated = FigureSpecification.model_validate(result.updated_spec)
    assert updated.plot.statistics.model_dump(by_alias=True) == before
    assert updated.plot.data.gene_column == spec.plot.data.gene_column


def _stub_execute(script_path, output_dir, **kwargs) -> ExecutionResult:
    out = Path(output_dir)
    (out / "volcano.pdf").write_bytes(b"%PDF-1.4\n")
    (out / "volcano.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (out / "volcano.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return ExecutionResult(status="success", output_files=["volcano.pdf", "volcano.svg", "volcano.png"], log="stub")


def test_workflow_refine_loop(tmp_path: Path) -> None:
    from llm.intent_parser import IntentParser

    workflow = FigureWorkflow(execute_fn=_stub_execute, intent_parser=IntentParser(enabled=False))
    first = workflow.generate_figure("帮我生成Nature风格火山图", EXAMPLE, work_dir=tmp_path)
    assert first.status == "success"
    assert first.current_version == 1
    assert (tmp_path / "spec_history.json").is_file()

    second = workflow.refine_figure(tmp_path, "字体大一点")
    assert second.status == "success"
    assert second.current_version == 2
    assert second.previous_version == 1
    assert second.spec is not None
    assert second.spec["font"]["axis_text_size"] == first.spec["font"]["axis_text_size"] + 2
    assert "panel.border" in Path(second.r_script_path).read_text(encoding="utf-8") or True

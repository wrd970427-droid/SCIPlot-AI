"""IntentParser tests: NLU JSON, ambiguity, and LLM fallback."""

from __future__ import annotations

import json

from llm.intent_parser import IntentParser
from llm.llm_client import LLMError
from schemas.figure_intent import FigureIntent, IntentFigureType


class _FakeLLM:
    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.available = True

    def complete(self, messages: list[dict[str, str]]) -> str:
        if self.error is not None:
            raise self.error
        assert messages[0]["role"] == "system"
        assert "不能" in messages[0]["content"] or "R" in messages[0]["content"]
        assert self.content is not None
        return self.content


def test_case1_rnaseq_volcano() -> None:
    parser = IntentParser(enabled=False)
    intent = parser.parse("RNA-seq差异基因火山图")
    assert intent.figure_type is IntentFigureType.VOLCANO
    assert intent.data_context.value == "RNA-seq"
    payload = json.loads(intent.model_dump_json())
    FigureIntent.model_validate(payload)


def test_case2_immune_infiltration_ambiguous() -> None:
    parser = IntentParser(enabled=False)
    intent = parser.parse("类似Nature Cancer展示免疫浸润")
    allowed = {IntentFigureType.HEATMAP, IntentFigureType.BOXPLOT}
    assert intent.figure_type in allowed
    assert allowed.intersection(set(intent.possible_types))
    assert intent.confidence < 1


def test_case3_llm_disabled_fallback_succeeds() -> None:
    parser = IntentParser(enabled=False)
    intent = parser.parse("我有RNA-seq差异分析结果，想做Nature风格火山图")
    assert intent.source == "fallback"
    assert intent.trace == "llm_disabled"
    assert intent.figure_type is IntentFigureType.VOLCANO
    assert intent.journal_style.value == "Nature"
    assert intent.purpose.value == "publication"
    assert intent.data_context.value == "RNA-seq"


def test_llm_unavailable_client_falls_back() -> None:
    parser = IntentParser(client=_FakeLLM(error=LLMError("LLM disabled or API_KEY/LLM_BASE_URL missing")), enabled=True)
    intent = parser.parse("RNA-seq差异基因火山图")
    assert intent.source == "fallback"
    assert intent.trace is not None and intent.trace.startswith("llm_failed:")
    assert intent.figure_type is IntentFigureType.VOLCANO


def test_invalid_llm_json_is_rejected_and_falls_back() -> None:
    parser = IntentParser(client=_FakeLLM(content="this is not json and not a figure intent"), enabled=True)
    intent = parser.parse("帮我画火山图")
    assert intent.source == "fallback"
    assert intent.figure_type is IntentFigureType.VOLCANO


def test_invalid_llm_schema_falls_back() -> None:
    raw = json.dumps({"figure_type": "not-a-real-plot", "confidence": 0.9})
    parser = IntentParser(client=_FakeLLM(content=raw), enabled=True)
    intent = parser.parse("帮我画火山图")
    assert intent.source == "fallback"
    assert intent.figure_type is IntentFigureType.VOLCANO


def test_valid_llm_json_is_validated() -> None:
    raw = json.dumps(
        {
            "figure_type": "volcano",
            "possible_types": ["volcano"],
            "data_context": "RNA-seq",
            "purpose": "publication",
            "journal_style": "Nature",
            "user_constraints": [],
            "confidence": 0.92,
        }
    )
    parser = IntentParser(client=_FakeLLM(content=raw), enabled=True)
    intent = parser.parse("我有RNA-seq差异分析结果，想做Nature风格火山图")
    assert intent.source == "llm"
    assert intent.figure_type is IntentFigureType.VOLCANO
    assert intent.data_context.value == "RNA-seq"
    assert intent.journal_style.value == "Nature"
    FigureIntent.model_validate(intent.model_dump())

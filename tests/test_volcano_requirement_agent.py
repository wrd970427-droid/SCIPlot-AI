"""Volcano Requirement Agent tests (V0.1)."""

from __future__ import annotations

from agents.knowledge_loader import load_volcano_rules
from agents.volcano_requirement_agent import RequirementStatus, VolcanoRequirementAgent
from schemas.figure_spec import FigureSpecification, FigureType, JournalStyle


def _knowledge_questions() -> set[str]:
    rules = load_volcano_rules()
    return {item["question"] for item in rules["user_questions"]}


def test_case1_plain_volcano_asks_missing_parameters() -> None:
    agent = VolcanoRequirementAgent()
    response = agent.handle("帮我画一个火山图")

    assert response.figure_type == "volcano"
    assert response.status is RequirementStatus.NEED_INFORMATION
    assert response.specification is None
    for param in ["data_file", "gene_column", "log2FC_column", "pvalue_column"]:
        assert param in response.missing_parameters
    assert response.questions
    allowed = _knowledge_questions()
    for question in response.questions:
        assert question in allowed


def test_case2_nature_rnaseq_volcano_detects_journal() -> None:
    agent = VolcanoRequirementAgent()
    response = agent.handle("帮我画一个Nature风格RNA-seq火山图")

    assert response.figure_type == "volcano"
    assert response.journal_style == "Nature"
    assert response.status is RequirementStatus.NEED_INFORMATION
    assert response.known_parameters.get("journal_style") == "Nature"
    assert "data_file" in response.missing_parameters


def test_case3_complete_parameters_build_specification() -> None:
    agent = VolcanoRequirementAgent()
    response = agent.handle(
        "帮我画一个Nature风格RNA-seq火山图",
        answers={
            "data_file": "examples/example_volcano.csv",
            "gene_column": "gene",
            "log2FC_column": "log2FoldChange",
            "pvalue_column": "padj",
            "significance_metric": "FDR",
        },
    )

    assert response.status is RequirementStatus.READY
    assert response.missing_parameters == []
    assert response.questions == []
    assert response.specification is not None

    spec = FigureSpecification.model_validate(response.specification)
    assert spec.figure_type is FigureType.VOLCANO
    assert spec.journal_style is JournalStyle.NATURE
    assert spec.size.width_mm == 89
    assert spec.size.height_mm == 89
    assert spec.size.dpi == 600
    assert spec.font.font_family == "Arial"
    assert spec.plot.data.source == "examples/example_volcano.csv"
    assert spec.plot.data.gene_column == "gene"
    assert spec.plot.data.log2fc_column == "log2FoldChange"
    assert spec.plot.data.significance_column == "padj"
    assert spec.plot.statistics.log2fc_threshold == 1
    assert spec.plot.statistics.fdr_threshold == 0.05
    assert spec.is_complete_for_codegen()


def test_intent_allows_volcano_without_keyword() -> None:
    from schemas.figure_intent import FigureIntent, IntentFigureType

    agent = VolcanoRequirementAgent()
    intent = FigureIntent(
        figure_type=IntentFigureType.VOLCANO,
        data_context="RNA-seq",
        purpose="publication",
        journal_style="Nature",
        confidence=0.9,
        source="llm",
    )
    response = agent.handle("我有RNA-seq差异分析结果", intent=intent)
    assert response.status is not RequirementStatus.UNSUPPORTED
    assert response.figure_type == "volcano"
    assert response.journal_style == "Nature"
    assert "data_file" in response.missing_parameters

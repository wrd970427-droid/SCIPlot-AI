"""Parse natural language into FigureIntent. LLM optional; rules always available."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from core.column_mapper import map_columns_from_request
from llm.llm_client import LLMClient, LLMError
from llm.prompt_templates import SYSTEM_PROMPT, user_prompt_message
from schemas.figure_intent import (
    DataContext,
    FigureIntent,
    IntentFigureType,
    IntentJournal,
    IntentPurpose,
)

logger = logging.getLogger("sciplot.llm")

_TYPE_KEYWORDS: list[tuple[IntentFigureType, tuple[str, ...]]] = [
    (IntentFigureType.VOLCANO, ("火山图", "volcano", "deg plot", "差异基因", "差异表达")),
    (IntentFigureType.HEATMAP, ("热图", "heatmap", "免疫浸润", "immune infiltration", "ssgsea")),
    (IntentFigureType.SURVIVAL, ("生存曲线", "kaplan", "km曲线", "survival")),
    (IntentFigureType.ROC, ("roc", "auc曲线")),
    (IntentFigureType.BOXPLOT, ("箱线图", "boxplot", "箱型图")),
    (IntentFigureType.VIOLIN, ("小提琴", "violin")),
    (IntentFigureType.SCATTER, ("散点", "scatter")),
    (IntentFigureType.ENRICHMENT, ("富集", "gsea", "kegg", "go富集", "dotplot")),
    (IntentFigureType.ONCOPLOT, ("oncoplot", "瀑布图", "mutation lollipop", "maf")),
    (IntentFigureType.UMAP, ("umap", "tsne", "单细胞降维")),
]


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.I).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", stripped, flags=re.S)
    if not match:
        raise ValueError("LLM output is not JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("LLM JSON is not an object")
    return data


class IntentParser:
    """NLU entry point: LLM first, rule-based fallback on any failure."""

    def __init__(self, client: LLMClient | None = None, *, enabled: bool | None = None) -> None:
        self.client = client if client is not None else LLMClient()
        self.enabled = self.client.available if enabled is None else enabled

    def parse(self, user_prompt: str, *, available_columns: list[str] | None = None) -> FigureIntent:
        prompt = (user_prompt or "").strip()
        columns = [name for name in (available_columns or []) if name]
        if self.enabled:
            try:
                return self._parse_llm(prompt, available_columns=columns)
            except (LLMError, ValueError, json.JSONDecodeError, ValidationError) as exc:
                logger.warning("LLM intent parse failed; using rule fallback: %s", exc)
                fallback = self._parse_rules(prompt, available_columns=columns)
                fallback.trace = f"llm_failed:{type(exc).__name__}:{exc}"
                fallback.source = "fallback"
                return fallback
        intent = self._parse_rules(prompt, available_columns=columns)
        intent.source = "fallback"
        intent.trace = "llm_disabled"
        return intent

    def _parse_llm(self, prompt: str, *, available_columns: list[str] | None = None) -> FigureIntent:
        content = self.client.complete(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt_message(prompt, available_columns=available_columns)},
            ]
        )
        payload = extract_json_object(content)
        forbidden = ("ggplot", "ggsave", "library(", "ComplexHeatmap")
        blob = json.dumps(payload, ensure_ascii=False)
        if any(token.lower() in blob.lower() for token in forbidden):
            raise ValueError("LLM attempted to emit plotting code")
        allowed = set(FigureIntent.model_fields)
        payload = {key: value for key, value in payload.items() if key in allowed}
        intent = FigureIntent.model_validate({**payload, "source": "llm"})
        if not intent.possible_types:
            intent.possible_types = [intent.figure_type]
        if available_columns:
            remapped = map_columns_from_request(
                prompt,
                available_columns,
                extra=intent.data_mapping,
            )
            if remapped:
                intent.data_mapping = remapped
        return intent

    def _parse_rules(self, prompt: str, *, available_columns: list[str] | None = None) -> FigureIntent:
        compact = prompt.lower()
        hits: list[IntentFigureType] = []
        for figure_type, keywords in _TYPE_KEYWORDS:
            if any(key.lower() in compact or key in prompt for key in keywords):
                if figure_type not in hits:
                    hits.append(figure_type)

        if not hits:
            figure_type = IntentFigureType.VOLCANO
            confidence = 0.2
        elif len(hits) == 1:
            figure_type = hits[0]
            confidence = 0.86
        else:
            figure_type = hits[0]
            confidence = 0.55

        if "免疫浸润" in prompt or "immune infiltration" in compact:
            for extra in (IntentFigureType.HEATMAP, IntentFigureType.BOXPLOT):
                if extra not in hits:
                    hits.append(extra)
            if figure_type not in (IntentFigureType.HEATMAP, IntentFigureType.BOXPLOT):
                figure_type = IntentFigureType.HEATMAP
            confidence = min(confidence, 0.6)

        context = DataContext.UNKNOWN
        if any(token in compact for token in ("rna-seq", "rnaseq", "rna seq", "rna-seq", "转录组")) or "RNA-seq" in prompt or "差异基因" in prompt:
            context = DataContext.RNA_SEQ
        if any(token in compact for token in ("single-cell", "scrna", "单细胞", "umap")):
            context = DataContext.SINGLE_CELL
        if "tcga" in compact:
            context = DataContext.TCGA
        if any(token in compact for token in ("proteom", "蛋白组")):
            context = DataContext.PROTEOMICS
        if "microbiome" in compact or "微生物组" in prompt:
            context = DataContext.MICROBIOME

        journal = IntentJournal.CUSTOM
        if "nature" in compact:
            journal = IntentJournal.NATURE
        elif re.search(r"\bcell\b", compact) or "Cell" in prompt:
            journal = IntentJournal.CELL
        elif "science" in compact:
            journal = IntentJournal.SCIENCE

        purpose = IntentPurpose.PUBLICATION
        if any(token in prompt for token in ("探索", "看看", "internal")) or "explor" in compact:
            if "投稿" not in prompt and "nature" not in compact and "cell" not in compact:
                purpose = IntentPurpose.EXPLORATION
        if journal is not IntentJournal.CUSTOM:
            purpose = IntentPurpose.PUBLICATION

        constraints: list[str] = []
        if "nature cancer" in compact:
            constraints.append("Nature Cancer style")
        if "免疫浸润" in prompt:
            constraints.append("immune infiltration")

        possible = hits or [figure_type]
        if figure_type not in possible:
            possible = [figure_type, *possible]

        return FigureIntent(
            figure_type=figure_type,
            possible_types=possible,
            data_context=context,
            purpose=purpose,
            journal_style=journal,
            user_constraints=constraints,
            data_mapping=map_columns_from_request(prompt, list(available_columns or [])),
            confidence=confidence,
            source="fallback",
        )

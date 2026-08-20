"""Volcano Requirement Agent (V0.1).

Collects volcano-plot requirements from a user prompt and optional FigureIntent.
Does not generate R, execute plots, or change QC rules.
Questions and required slots come from knowledge/figure_rules/volcano.json.
Journal defaults come from knowledge/journals/journal_styles.json.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from agents.knowledge_loader import load_journal_styles, load_volcano_rules
from schemas.figure_intent import FigureIntent, IntentFigureType, IntentPurpose
from schemas.figure_spec import FigureSpecification, JournalStyle


class RequirementStatus(str, Enum):
    NEED_INFORMATION = "need_information"
    READY = "ready"
    UNSUPPORTED = "unsupported"


class RequirementResponse(BaseModel):
    """Structured output of the Requirement Agent."""

    model_config = ConfigDict(extra="forbid")

    figure_type: Optional[str] = None
    journal_style: Optional[str] = None
    missing_parameters: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    status: RequirementStatus
    known_parameters: dict[str, Any] = Field(default_factory=dict)
    specification: Optional[dict[str, Any]] = None


_SIGNIFICANCE_MAP = {
    "fdr": "fdr",
    "padj": "fdr",
    "adjusted p": "fdr",
    "p-value": "pvalue",
    "pvalue": "pvalue",
    "p value": "pvalue",
    "p值": "pvalue",
}

_COLUMN_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "log2FC_column": [
        re.compile(r"log2\s*fc\s*(?:列|column)?\s*(?:叫|是|为|对应)?\s*[:：]?\s*([A-Za-z0-9_.]+)", re.I),
        re.compile(r"log2FoldChange", re.I),
    ],
    "gene_column": [
        re.compile(r"基因(?:名|名称)?列\s*(?:叫|是|为)?\s*[:：]?\s*([A-Za-z0-9_.]+)", re.I),
        re.compile(r"gene(?:_name| symbol)?\s*(?:列|column)\s*[:：]?\s*([A-Za-z0-9_.]+)", re.I),
    ],
    "pvalue_column": [
        re.compile(r"(?:显著性|fdr|p-?value|pvalue)\s*(?:数值)?(?:所在)?列\s*(?:叫|是|为)?\s*[:：]?\s*([A-Za-z0-9_.]+)", re.I),
        re.compile(r"\b(padj|pvalue|p_value|p\.value|FDR|fdr)\b"),
    ],
    "data_file": [
        re.compile(r"(?:数据(?:文件)?|csv|tsv|table)\s*[:：]?\s*([^\s,，]+?\.(?:csv|tsv|txt))", re.I),
        re.compile(r"([^\s,，]+?\.(?:csv|tsv))", re.I),
    ],
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class VolcanoRequirementAgent:
    """Rule-based requirement collector for volcano plots."""

    def __init__(self, knowledge_root: str | None = None) -> None:
        self.rules = load_volcano_rules(knowledge_root)
        journals_doc = load_journal_styles(knowledge_root)
        self.journals: dict[str, Any] = journals_doc["journals"]
        self._required_ids = [item["id"] for item in self.rules["required_parameters"]]
        self._questions_by_id = {item["id"]: item for item in self.rules["user_questions"]}
        self._param_by_id = {item["id"]: item for item in self.rules["required_parameters"]}
        self._optional_by_id = {item["id"]: item for item in self.rules.get("optional_parameters", [])}

    def handle(
        self,
        user_prompt: str,
        answers: dict[str, Any] | None = None,
        intent: FigureIntent | None = None,
    ) -> RequirementResponse:
        """Parse a prompt (and optional slot answers / NLU intent) into questions or a spec."""
        prompt = _normalize(user_prompt or "")
        is_volcano = self._is_volcano(prompt)
        if intent is not None and intent.figure_type is IntentFigureType.VOLCANO:
            is_volcano = True
        if not is_volcano:
            return RequirementResponse(
                figure_type=intent.figure_type.value if intent is not None else None,
                status=RequirementStatus.UNSUPPORTED,
                questions=[],
                missing_parameters=[],
            )

        collected = self._collect_from_intent(intent)
        collected.update(self._extract_from_prompt(prompt))
        collected.update(self._normalize_answers(answers or {}))

        missing = [param_id for param_id in self._required_ids if not collected.get(param_id)]
        questions = self._questions_for(missing, collected)

        journal = collected.get("journal_style")
        if missing:
            return RequirementResponse(
                figure_type="volcano",
                journal_style=journal,
                missing_parameters=missing,
                questions=questions,
                status=RequirementStatus.NEED_INFORMATION,
                known_parameters=collected,
            )

        spec = self._build_specification(collected)
        return RequirementResponse(
            figure_type="volcano",
            journal_style=spec.journal_style.value,
            missing_parameters=[],
            questions=[],
            status=RequirementStatus.READY,
            known_parameters=collected,
            specification=spec.model_dump(mode="json", by_alias=True),
        )

    def _is_volcano(self, prompt: str) -> bool:
        lowered = prompt.lower()
        compact = lowered.replace(" ", "")
        aliases = list(self.rules["metadata"].get("aliases", []))
        for alias in aliases:
            token = alias.lower()
            if token in lowered or token.replace(" ", "") in compact:
                return True
        return False

    def _collect_from_intent(self, intent: FigureIntent | None) -> dict[str, Any]:
        if intent is None:
            return {}
        collected: dict[str, Any] = {
            "purpose": "publication" if intent.purpose is IntentPurpose.PUBLICATION else "internal",
        }
        journal = intent.journal_style.value
        if journal in self.journals or journal in {item.value for item in JournalStyle}:
            collected["journal_style"] = journal
        if intent.user_constraints:
            collected["user_constraints"] = list(intent.user_constraints)
        return collected

    def _extract_from_prompt(self, prompt: str) -> dict[str, Any]:
        collected: dict[str, Any] = {}
        journal = self._detect_journal(prompt)
        if journal:
            collected["journal_style"] = journal
            collected["purpose"] = "publication"

        lowered = prompt.lower()
        if re.search(r"单栏|single\s*column", prompt, re.I):
            collected["output_size"] = "single"
        elif re.search(r"双栏|double\s*column", prompt, re.I):
            collected["output_size"] = "double"

        if re.search(r"\bfdr\b|padj|校正.?p", lowered):
            collected["significance_metric"] = "fdr"
        elif re.search(r"p-?value|pvalue|p值|原始p", lowered):
            collected["significance_metric"] = "pvalue"

        for param_id, patterns in _COLUMN_PATTERNS.items():
            if collected.get(param_id):
                continue
            for pattern in patterns:
                match = pattern.search(prompt)
                if not match:
                    continue
                if match.lastindex:
                    collected[param_id] = match.group(1)
                elif param_id == "log2FC_column" and re.search(r"log2FoldChange", prompt, re.I):
                    collected[param_id] = "log2FoldChange"
                elif param_id == "pvalue_column" and match.group(0):
                    collected[param_id] = match.group(0)
                break

        return collected

    def _detect_journal(self, prompt: str) -> Optional[str]:
        compact = re.sub(r"[\s\-]", "", prompt).lower()
        names = sorted(self.journals.keys(), key=len, reverse=True)
        for name in names:
            needle = re.sub(r"[\s\-]", "", name).lower()
            if needle and needle in compact:
                return name
        return None

    def _normalize_answers(self, answers: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, raw in answers.items():
            param_id = self._resolve_param_id(key)
            if param_id is None or raw is None or raw == "":
                continue
            value = raw
            if param_id == "significance_metric":
                value = _SIGNIFICANCE_MAP.get(str(raw).strip().lower(), str(raw).strip().lower())
            elif param_id == "output_size":
                text = str(raw).lower()
                if "double" in text or "双" in text:
                    value = "double"
                elif "single" in text or "单" in text:
                    value = "single"
                else:
                    value = "custom"
            elif param_id == "journal_style":
                value = self._detect_journal(str(raw)) or raw
            out[param_id] = value
        return out

    def _resolve_param_id(self, key: str) -> Optional[str]:
        if key in self._param_by_id or key in self._questions_by_id or key in self._optional_by_id:
            return key
        if key in {"purpose", "journal_style", "output_size", "significance_metric"}:
            return key
        for item in self.rules["required_parameters"] + self.rules.get("optional_parameters", []):
            if item.get("spec_path") == key:
                return item["id"]
        return None

    def _questions_for(self, missing: list[str], collected: dict[str, Any]) -> list[str]:
        """Render questions from volcano.json; never hard-code the question text."""
        ask_ids: list[str] = []
        for question in self.rules["user_questions"]:
            qid = question["id"]
            if question.get("skip_if_known") and collected.get(qid):
                continue
            if qid in missing:
                ask_ids.append(qid)
                continue
            if qid == "significance_metric" and "pvalue_column" in missing and "significance_metric" not in collected:
                ask_ids.append(qid)

        questions: list[str] = []
        for qid in ask_ids:
            item = self._questions_by_id.get(qid)
            if item:
                questions.append(item["question"])
        return questions

    def _build_specification(self, collected: dict[str, Any]) -> FigureSpecification:
        defaults = {k: v for k, v in self.rules["default_parameters"].items() if not str(k).startswith("_")}
        payload: dict[str, Any] = {
            "figure_type": "volcano",
            "purpose": collected.get("purpose", "publication"),
            "geometry": {
                "point_size": defaults.get("point_size", 1.5),
                "line_width": defaults.get("line_width", 0.5),
                "threshold_line_width": defaults.get("threshold_line_width", 0.35),
                "alpha": defaults.get("alpha", 0.7),
            },
            "plot": {
                "figure_type": "volcano",
                "data": {
                    "source": collected.get("data_file"),
                    "log2fc_column": collected.get("log2FC_column"),
                    "significance_column": collected.get("pvalue_column"),
                    "gene_column": collected.get("gene_column"),
                },
                "statistics": {
                    "log2FC_threshold": defaults.get("log2FC_threshold", 1),
                    "FDR_threshold": defaults.get("FDR_threshold", 0.05),
                    "significance_metric": collected.get(
                        "significance_metric", defaults.get("significance_metric", "fdr")
                    ),
                },
                "labels": {
                    "enabled": bool(defaults.get("label_enabled", False)),
                    "top_n": defaults.get("label_top_genes", 10),
                },
                "colors": defaults.get("colors", {}),
            },
        }

        journal_name = collected.get("journal_style")
        if journal_name and journal_name in self.journals:
            spec_defaults = self.journals[journal_name].get("spec_defaults", {})
            payload = _deep_merge(payload, spec_defaults)
            if journal_name in {item.value for item in JournalStyle}:
                payload["journal_style"] = journal_name
            else:
                payload["journal_style"] = "Custom"
        elif journal_name:
            payload["journal_style"] = "Custom"

        column = collected.get("output_size")
        if column:
            size = dict(payload.get("size") or {})
            size["column"] = column
            payload["size"] = size

        return FigureSpecification.model_validate(payload)

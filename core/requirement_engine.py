"""Generic Requirement Engine — driven only by FigureDefinition fields."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from core.column_mapper import map_columns_from_request
from schemas.figure_definition import FigureDefinition


class GenericRequirementStatus(str, Enum):
    NEED_INFORMATION = "need_information"
    READY = "ready"
    UNSUPPORTED = "unsupported"


class GenericRequirementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    figure_definition_id: str
    data_schema_id: str
    status: GenericRequirementStatus
    missing_fields: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    known_mapping: dict[str, Any] = Field(default_factory=dict)
    statistics: dict[str, Any] = Field(default_factory=dict)
    visual_parameters: dict[str, Any] = Field(default_factory=dict)
    style_profile: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


# Common column-name hints by semantic role (not figure-type branches).
ROLE_COLUMN_HINTS: dict[str, tuple[str, ...]] = {
    "feature_id": ("gene", "gene_id", "symbol", "feature", "id", "gene_name"),
    "effect_size": ("log2foldchange", "log2fc", "logfc", "log_fc", "effect", "estimate"),
    "significance": ("padj", "fdr", "qvalue", "q_value", "pvalue", "p_value", "p.value", "pval"),
    "group": ("group", "condition", "cluster", "identity", "subtype"),
    "value": ("value", "expression", "abundance", "score"),
    "x": ("x", "lfc", "logfc", "log2fc", "log2foldchange"),
    "y": ("y", "pvalue", "p-value", "padj", "fdr"),
    "size": ("size", "goodsgrna", "count", "n", "weight"),
    "time": ("time", "os_time", "survival_time", "days"),
    "status": ("status", "event", "os_status", "fustat"),
}


class RequirementEngine:
    """Collect data role mappings from answers / column hints using FigureDefinition."""

    def collect(
        self,
        definition: FigureDefinition,
        *,
        answers: dict[str, Any] | None = None,
        available_columns: list[str] | None = None,
        user_request: str = "",
    ) -> GenericRequirementResponse:
        answers = dict(answers or {})
        columns = list(available_columns or [])
        column_lookup = {name.lower(): name for name in columns if name}
        if user_request:
            for role, col in map_columns_from_request(user_request, columns).items():
                answers.setdefault(role, col)

        known: dict[str, Any] = {}
        # Explicit role answers preferred.
        for field in list(definition.required_fields) + list(definition.optional_fields):
            role = field.role
            if role in answers and answers[role]:
                known[role] = answers[role]
                continue
            # Accept aliases like feature_id_column
            alias = f"{role}_column"
            if alias in answers and answers[alias]:
                known[role] = answers[alias]
                continue
            # Infer required roles from headers; optional only if user/prompt provided.
            if field in definition.required_fields:
                hint = self._infer_column(role, column_lookup)
                if hint:
                    known[role] = hint

        # Optional data_source convenience.
        if answers.get("data_file"):
            known["data_source"] = answers["data_file"]
        elif answers.get("data_source"):
            known["data_source"] = answers["data_source"]

        missing = [field.role for field in definition.required_fields if not known.get(field.role)]
        questions = [
            f"Please provide the column/field for role '{role}' "
            f"(type={next(f.type for f in definition.required_fields if f.role == role)})."
            for role in missing
        ]

        statistics = {
            item.name: answers.get(item.name, item.default)
            for item in definition.statistical_parameters
        }
        visual = {
            item.name: answers.get(item.name, item.default)
            for item in definition.visual_parameters
        }
        style = {}
        if answers.get("journal_style"):
            style["journal_style"] = answers["journal_style"]
        if answers.get("purpose"):
            style["purpose"] = answers["purpose"]

        if missing:
            return GenericRequirementResponse(
                figure_definition_id=definition.id,
                data_schema_id=definition.data_schema_id,
                status=GenericRequirementStatus.NEED_INFORMATION,
                missing_fields=missing,
                questions=questions,
                known_mapping=known,
                statistics={k: v for k, v in statistics.items() if v is not None},
                visual_parameters={k: v for k, v in visual.items() if v is not None},
                style_profile=style,
                message="Required information missing",
            )

        return GenericRequirementResponse(
            figure_definition_id=definition.id,
            data_schema_id=definition.data_schema_id,
            status=GenericRequirementStatus.READY,
            missing_fields=[],
            questions=[],
            known_mapping=known,
            statistics={k: v for k, v in statistics.items() if v is not None},
            visual_parameters={k: v for k, v in visual.items() if v is not None},
            style_profile=style,
            message="ready",
        )

    @staticmethod
    def _infer_column(role: str, column_lookup: dict[str, str]) -> Optional[str]:
        hints = ROLE_COLUMN_HINTS.get(role, ())
        for hint in hints:
            if hint in column_lookup:
                return column_lookup[hint]
        # Soft contains match.
        for lowered, original in column_lookup.items():
            if any(hint in lowered for hint in hints):
                return original
        return None

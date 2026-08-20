"""LLM Figure Intent — NLU output only. Never contains R code."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IntentFigureType(str, Enum):
    VOLCANO = "volcano"
    HEATMAP = "heatmap"
    SURVIVAL = "survival"
    ROC = "roc"
    BOXPLOT = "boxplot"
    VIOLIN = "violin"
    SCATTER = "scatter"
    ENRICHMENT = "enrichment"
    ONCOPLOT = "oncoplot"
    UMAP = "umap"


class DataContext(str, Enum):
    RNA_SEQ = "RNA-seq"
    SINGLE_CELL = "single-cell"
    TCGA = "TCGA"
    PROTEOMICS = "proteomics"
    MICROBIOME = "microbiome"
    UNKNOWN = "unknown"


class IntentPurpose(str, Enum):
    PUBLICATION = "publication"
    EXPLORATION = "exploration"


class IntentJournal(str, Enum):
    NATURE = "Nature"
    CELL = "Cell"
    SCIENCE = "Science"
    CUSTOM = "Custom"


class FigureIntent(BaseModel):
    """Structured research-figure intent extracted from natural language."""

    model_config = ConfigDict(extra="forbid")

    figure_type: IntentFigureType
    possible_types: list[IntentFigureType] = Field(default_factory=list)
    data_context: DataContext = DataContext.UNKNOWN
    purpose: IntentPurpose = IntentPurpose.PUBLICATION
    journal_style: IntentJournal = IntentJournal.CUSTOM
    user_constraints: list[str] = Field(default_factory=list)
    data_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Optional aesthetic roles (x/y/size/group) → column names. Never row values.",
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: Literal["llm", "fallback"] = "fallback"
    trace: Optional[str] = None

    @field_validator("figure_type", mode="before")
    @classmethod
    def _normalize_figure_type(cls, value: object) -> object:
        return _normalize_type_token(value)

    @field_validator("possible_types", mode="before")
    @classmethod
    def _normalize_possible_types(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, list):
            return [_normalize_type_token(item) for item in value]
        return value

    @field_validator("data_context", mode="before")
    @classmethod
    def _normalize_context(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        mapping = {
            "rnaseq": "RNA-seq",
            "rna-seq": "RNA-seq",
            "rna seq": "RNA-seq",
            "scrna": "single-cell",
            "scRNA-seq": "single-cell",
            "single cell": "single-cell",
            "single-cell": "single-cell",
        }
        return mapping.get(text.lower(), text)

    @field_validator("journal_style", mode="before")
    @classmethod
    def _normalize_journal(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        lowered = text.lower()
        aliases = {
            "nature cancer": "Nature",
            "nature communications": "Nature",
            "cancer cell": "Cell",
        }
        if lowered in aliases:
            return aliases[lowered]
        allowed = {item.value for item in IntentJournal}
        return text if text in allowed else "Custom"


def _normalize_type_token(value: object) -> object:
    if not isinstance(value, str):
        return value
    token = value.strip().lower().replace(" ", "_")
    aliases = {
        "roc": "roc",
        "kaplan_meier": "survival",
        "km": "survival",
        "survival": "survival",
        "enrichment_dotplot": "enrichment",
        "dotplot": "enrichment",
        "gsea": "enrichment",
        "deg": "volcano",
        "volcano_plot": "volcano",
    }
    return aliases.get(token, token)

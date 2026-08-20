"""Generic Figure Specification — catalog-driven, figure-agnostic payload."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class GenericFigureSpecification(BaseModel):
    """Unified Spec produced by SpecificationBuilder for any catalog figure."""

    model_config = ConfigDict(extra="forbid")

    spec_version: str = "0.2.0"
    figure_definition_id: str
    data_schema_id: str
    data_mapping: dict[str, str] = Field(default_factory=dict)
    data_source: Optional[str] = None
    statistics: dict[str, Any] = Field(default_factory=dict)
    visual_parameters: dict[str, Any] = Field(default_factory=dict)
    style_profile: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(
        default_factory=lambda: {"pdf": True, "svg": True, "png": True}
    )
    qc_requirement: dict[str, Any] = Field(default_factory=dict)
    # Optional bridge payload for legacy volcano FigureSpecification JSON.
    legacy_volcano_spec: Optional[dict[str, Any]] = None

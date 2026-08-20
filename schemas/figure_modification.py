"""Figure design-parameter modification records (refinement only)."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class FigureModification(BaseModel):
    """One targeted design-parameter change. Never carries analysis changes."""

    model_config = ConfigDict(extra="forbid")

    target_parameter: str = Field(
        ...,
        description="Logical or dotted Spec path, e.g. point_size or font.axis_text_size.",
    )
    old_value: Optional[Any] = None
    new_value: Any = None
    reason: str = ""
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class ModificationRequest(BaseModel):
    """Parsed NL refinement request before Spec patching."""

    model_config = ConfigDict(extra="forbid")

    modifications: list[FigureModification] = Field(default_factory=list)
    unmatched: bool = False
    message: str = ""

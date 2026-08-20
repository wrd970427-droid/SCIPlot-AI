"""QC report schema. The QC agent never mutates FigureSpecification or figure files."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class QCStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAILED = "failed"


class QCChecks(BaseModel):
    """Per-rule verdicts. Values are pass / warning / failed."""

    model_config = ConfigDict(extra="forbid")

    file_check: str = "pass"
    dimension_check: str = "pass"
    resolution_check: str = "pass"
    font_check: str = "pass"
    parameter_check: str = "pass"


class QCReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: QCStatus
    checks: QCChecks
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

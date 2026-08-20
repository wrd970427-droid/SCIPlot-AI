"""Spec version history with undo / redo for design refinements."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from schemas.figure_modification import FigureModification
from schemas.figure_spec import FigureSpecification


class SpecVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    label: str = ""
    spec: dict[str, Any]
    modifications: list[FigureModification] = Field(default_factory=list)
    note: str = ""
    r_code: str = ""


class SpecHistory(BaseModel):
    """Linear history of FigureSpecification snapshots (optional R snapshots)."""

    model_config = ConfigDict(extra="forbid")

    versions: list[SpecVersion] = Field(default_factory=list)
    current_index: int = Field(default=-1, ge=-1)

    @classmethod
    def from_initial(
        cls,
        spec: FigureSpecification | dict[str, Any],
        *,
        note: str = "initial",
        r_code: str = "",
    ) -> "SpecHistory":
        payload = _spec_dict(spec)
        history = cls()
        history.push(payload, modifications=[], note=note, label="Version 1", r_code=r_code)
        return history

    @property
    def current_version(self) -> int:
        if self.current_index < 0 or not self.versions:
            return 0
        return self.versions[self.current_index].version

    def current_spec(self) -> dict[str, Any]:
        if self.current_index < 0 or not self.versions:
            raise ValueError("SpecHistory is empty")
        return self.versions[self.current_index].spec

    def current_r_code(self) -> str:
        if self.current_index < 0 or not self.versions:
            return ""
        return self.versions[self.current_index].r_code or ""

    def push(
        self,
        spec: FigureSpecification | dict[str, Any],
        *,
        modifications: list[FigureModification] | None = None,
        note: str = "",
        label: str | None = None,
        r_code: str = "",
    ) -> SpecVersion:
        payload = _spec_dict(spec)
        # Drop redo branch when pushing after undo.
        if self.current_index >= 0 and self.current_index < len(self.versions) - 1:
            self.versions = self.versions[: self.current_index + 1]
        version_no = len(self.versions) + 1
        entry = SpecVersion(
            version=version_no,
            label=label or f"Version {version_no}",
            spec=payload,
            modifications=list(modifications or []),
            note=note,
            r_code=r_code or "",
        )
        self.versions.append(entry)
        self.current_index = len(self.versions) - 1
        return entry

    def undo(self) -> Optional[SpecVersion]:
        if self.current_index <= 0:
            return None
        self.current_index -= 1
        return self.versions[self.current_index]

    def redo(self) -> Optional[SpecVersion]:
        if self.current_index >= len(self.versions) - 1:
            return None
        self.current_index += 1
        return self.versions[self.current_index]

    def summary(self) -> dict[str, Any]:
        return {
            "current_version": self.current_version,
            "total_versions": len(self.versions),
            "can_undo": self.current_index > 0,
            "can_redo": self.current_index < len(self.versions) - 1,
            "versions": [
                {
                    "version": item.version,
                    "label": item.label,
                    "note": item.note,
                    "has_r_code": bool(item.r_code),
                    "modifications": [m.model_dump(mode="json") for m in item.modifications],
                }
                for item in self.versions
            ],
        }


def _spec_dict(spec: FigureSpecification | dict[str, Any]) -> dict[str, Any]:
    if hasattr(spec, "model_dump") and not isinstance(spec, dict):
        return spec.model_dump(mode="json", by_alias=True)
    return dict(spec)

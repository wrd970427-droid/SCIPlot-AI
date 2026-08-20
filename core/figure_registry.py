"""Figure Registry — catalog metadata only (no R code)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from knowledge.scientific_figures.loader import load_catalog, load_taxonomy
from schemas.figure_definition import FigureDefinition, ImplementationStatus

EXECUTABLE_STATUSES = {
    ImplementationStatus.CODE_GENERATION_READY,
    ImplementationStatus.EXECUTION_VERIFIED,
    ImplementationStatus.QC_VERIFIED,
}


@dataclass(frozen=True)
class FigureMetadata:
    """Lightweight catalog row for retrieval / gating."""

    id: str
    name: str
    category: str
    data_schema_id: str
    recommended_r_packages: tuple[str, ...]
    implementation_status: ImplementationStatus
    capability_level: str
    retrieval_keywords: tuple[str, ...]
    scientific_questions: tuple[str, ...]

    @property
    def is_executable(self) -> bool:
        return self.implementation_status in EXECUTABLE_STATUSES


class FigureRegistry:
    """Load Scientific Figure Catalog metadata into memory."""

    def __init__(self, definitions: list[FigureDefinition] | None = None) -> None:
        self._definitions = {item.id: item for item in (definitions or load_catalog())}
        self._taxonomy = load_taxonomy()

    def get_figure_definition(self, figure_id: str) -> FigureDefinition:
        if figure_id not in self._definitions:
            raise KeyError(f"Unknown figure_id: {figure_id}")
        return self._definitions[figure_id]

    def get_metadata(self, figure_id: str) -> FigureMetadata:
        definition = self.get_figure_definition(figure_id)
        return self._to_metadata(definition)

    def list_available_figures(self) -> list[FigureMetadata]:
        return [self._to_metadata(item) for item in self._definitions.values()]

    def get_by_category(self, category: str) -> list[FigureMetadata]:
        return [
            self._to_metadata(item)
            for item in self._definitions.values()
            if item.category == category
        ]

    def search_figures(self, query: str) -> list[FigureMetadata]:
        text = (query or "").strip().lower()
        if not text:
            return []
        hits: list[tuple[int, FigureMetadata]] = []
        for definition in self._definitions.values():
            score = 0
            blob = " ".join(
                [
                    definition.id,
                    definition.name,
                    definition.category,
                    " ".join(definition.retrieval_keywords),
                    " ".join(definition.scientific_questions),
                    " ".join(definition.user_intent_examples),
                ]
            ).lower()
            if text in blob:
                score += 5
            for token in text.replace(",", " ").split():
                if token and token in blob:
                    score += 1
            if score:
                hits.append((score, self._to_metadata(definition)))
        hits.sort(key=lambda item: (-item[0], item[1].id))
        return [meta for _, meta in hits]

    def is_executable(self, figure_id: str) -> bool:
        return self.get_metadata(figure_id).is_executable

    @staticmethod
    def _to_metadata(definition: FigureDefinition) -> FigureMetadata:
        return FigureMetadata(
            id=definition.id,
            name=definition.name,
            category=definition.category,
            data_schema_id=definition.data_schema_id,
            recommended_r_packages=tuple(definition.recommended_r_packages),
            implementation_status=definition.implementation_status,
            capability_level=definition.capability_level.value,
            retrieval_keywords=tuple(definition.retrieval_keywords),
            scientific_questions=tuple(definition.scientific_questions),
        )

"""Code generation strategy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from schemas.generic_figure_spec import GenericFigureSpecification


class CodeGenerationStrategy(ABC):
    """One strategy per implemented figure family (or family group)."""

    figure_definition_id: str

    @abstractmethod
    def generate(
        self,
        spec: GenericFigureSpecification,
        output_path: str | Path | None = None,
    ) -> str:
        raise NotImplementedError

"""Code generation engine — strategy registry, no LLM."""

from __future__ import annotations

from pathlib import Path

from core.strategies.base import CodeGenerationStrategy
from core.strategies.boxplot_strategy import BoxplotStrategy
from core.strategies.scatter_strategy import ScatterStrategy
from core.strategies.volcano_strategy import VolcanoStrategy
from schemas.generic_figure_spec import GenericFigureSpecification


class CodeGenerationEngine:
    """Dispatch GenericFigureSpecification → R source via registered strategies."""

    def __init__(self, strategies: list[CodeGenerationStrategy] | None = None) -> None:
        self._strategies: dict[str, CodeGenerationStrategy] = {}
        defaults = strategies if strategies is not None else [
            VolcanoStrategy(),
            BoxplotStrategy(),
            ScatterStrategy(),
        ]
        for strategy in defaults:
            self.register(strategy)

    def register(self, strategy: CodeGenerationStrategy) -> None:
        self._strategies[strategy.figure_definition_id] = strategy

    def supported_figures(self) -> list[str]:
        return sorted(self._strategies)

    def generate(
        self,
        figure_specification: GenericFigureSpecification,
        output_path: str | Path | None = None,
    ) -> str:
        figure_id = figure_specification.figure_definition_id
        strategy = self._strategies.get(figure_id)
        if strategy is None:
            raise ValueError(
                f"No code-generation strategy registered for '{figure_id}'. "
                f"Available: {self.supported_figures()}"
            )
        return strategy.generate(figure_specification, output_path=output_path)

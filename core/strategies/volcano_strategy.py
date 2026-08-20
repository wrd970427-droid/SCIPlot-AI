"""Volcano code-generation strategy (uses legacy VolcanoRCodeAgent via adapter)."""

from __future__ import annotations

from pathlib import Path

from core.adapters.volcano_adapter import VolcanoAdapter
from core.strategies.base import CodeGenerationStrategy
from schemas.generic_figure_spec import GenericFigureSpecification


class VolcanoStrategy(CodeGenerationStrategy):
    figure_definition_id = "transcriptomics.volcano"

    def __init__(self, adapter: VolcanoAdapter | None = None) -> None:
        self.adapter = adapter or VolcanoAdapter()

    def generate(
        self,
        spec: GenericFigureSpecification,
        output_path: str | Path | None = None,
    ) -> str:
        if spec.figure_definition_id != self.figure_definition_id:
            raise ValueError(
                f"VolcanoStrategy only supports {self.figure_definition_id}, "
                f"got {spec.figure_definition_id}"
            )
        return self.adapter.generate_r(spec, output_path=output_path)

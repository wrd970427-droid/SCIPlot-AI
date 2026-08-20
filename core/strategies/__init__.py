"""Strategy package for figure-specific R generation."""

from core.strategies.base import CodeGenerationStrategy
from core.strategies.boxplot_strategy import BoxplotStrategy
from core.strategies.scatter_strategy import ScatterStrategy
from core.strategies.volcano_strategy import VolcanoStrategy

__all__ = ["BoxplotStrategy", "CodeGenerationStrategy", "ScatterStrategy", "VolcanoStrategy"]

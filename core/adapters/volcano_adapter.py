"""Adapter: GenericFigureSpecification ↔ legacy volcano agents."""

from __future__ import annotations

from typing import Any

from agents.volcano_r_code_agent import VolcanoRCodeAgent
from schemas.figure_spec import FigureSpecification
from schemas.generic_figure_spec import GenericFigureSpecification


# Semantic roles (catalog) → volcano FigureSpecification field paths / names.
ROLE_TO_VOLCANO_COLUMN = {
    "feature_id": "gene_column",
    "effect_size": "log2fc_column",
    "significance": "significance_column",
}


class VolcanoAdapter:
    """Bridge generic Spec to existing VolcanoRCodeAgent without rewriting it."""

    def __init__(self, r_code_agent: VolcanoRCodeAgent | None = None) -> None:
        self.r_code_agent = r_code_agent or VolcanoRCodeAgent()

    def to_legacy_spec(self, generic: GenericFigureSpecification) -> FigureSpecification:
        if generic.legacy_volcano_spec is not None:
            return FigureSpecification.model_validate(generic.legacy_volcano_spec)

        mapping = generic.data_mapping
        visual = generic.visual_parameters
        stats = generic.statistics
        style = generic.style_profile

        gene_col = mapping.get("feature_id")
        log2fc_col = mapping.get("effect_size")
        sig_col = mapping.get("significance")
        if not gene_col or not log2fc_col or not sig_col:
            raise ValueError("VolcanoAdapter requires feature_id, effect_size, significance mapping")

        metric = str(stats.get("significance_metric", "fdr")).lower()
        if metric in {"fdr", "padj", "qvalue"}:
            metric = "fdr"
        else:
            metric = "pvalue"

        journal = style.get("journal_style", "Nature")
        purpose = style.get("purpose", "publication")
        payload: dict[str, Any] = {
            "figure_type": "volcano",
            "purpose": purpose if purpose in {"publication", "internal"} else "publication",
            "journal_style": journal if journal in {
                "Nature", "Cell", "Science", "Nature Communications",
                "Cancer Cell", "Microbiome", "mSystems", "Custom",
            } else "Custom",
            "size": {
                "column": style.get("column", "single"),
                "width_mm": visual.get("width_mm", 89),
                "height_mm": visual.get("height_mm", 70),
                "dpi": visual.get("dpi", 600),
            },
            "font": {
                "font_family": visual.get("font_family", "Arial"),
                "axis_text_size": visual.get("font_size", visual.get("axis_text_size", 7)),
                "axis_title_size": visual.get("axis_title_size", visual.get("font_size", 8)),
                "legend_size": visual.get("legend_size", visual.get("font_size", 7)),
                "title_size": visual.get("title_size", visual.get("font_size", 8)),
            },
            "theme": {
                "background": "white",
                "grid": visual.get("grid", "none"),
                "border": visual.get("border", "none"),
                "legend_position": visual.get("legend_position", "right"),
            },
            "geometry": {
                "point_size": visual.get("point_size", 1.5),
                "line_width": visual.get("line_width", 0.5),
                "threshold_line_width": visual.get("threshold_line_width", 0.35),
                "alpha": visual.get("alpha", 0.7),
            },
            "output": generic.output or {"pdf": True, "svg": True, "png": True},
            "plot": {
                "figure_type": "volcano",
                "data": {
                    "source": generic.data_source or "input.csv",
                    "gene_column": gene_col,
                    "log2fc_column": log2fc_col,
                    "significance_column": sig_col,
                },
                "statistics": {
                    "log2FC_threshold": stats.get("log2FC_threshold", 1.0),
                    "FDR_threshold": stats.get("significance_threshold", stats.get("FDR_threshold", 0.05)),
                    "significance_metric": metric,
                },
                "labels": {
                    "enabled": bool(visual.get("label_repel", visual.get("label_count", 0))),
                    "mode": "top_n" if visual.get("label_count", 10) else "none",
                    "top_n": int(visual.get("label_count", 10) or 10),
                    "genes": [],
                },
                "colors": {
                    "up": visual.get("up_color", "#E64B35"),
                    "down": visual.get("down_color", "#4DBBD5"),
                    "ns": visual.get("neutral_color", "#B0B0B0"),
                },
            },
        }
        return FigureSpecification.model_validate(payload)

    def generate_r(self, generic: GenericFigureSpecification, output_path=None) -> str:
        legacy = self.to_legacy_spec(generic)
        return self.r_code_agent.generate(legacy, output_path=output_path)

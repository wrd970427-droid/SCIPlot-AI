"""Volcano R Code Agent tests (V0.1). Does not execute R."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from agents.volcano_r_code_agent import VolcanoRCodeAgent
from schemas.figure_spec import FigureSpecification, load_figure_specification

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "schemas" / "examples" / "volcano_nature_rnaseq.json"


def _example_spec() -> FigureSpecification:
    return load_figure_specification(EXAMPLE.read_text(encoding="utf-8"))


def test_generate_requires_figure_specification_not_prompt() -> None:
    params = inspect.signature(VolcanoRCodeAgent.generate).parameters
    assert "spec" in params
    assert "user_prompt" not in params
    assert "prompt" not in params


def test_generated_r_contains_required_ggplot_pieces(tmp_path: Path) -> None:
    spec = _example_spec()
    agent = VolcanoRCodeAgent()
    out = tmp_path / "volcano.R"
    code = agent.generate(spec, output_path=out)

    assert out.is_file()
    assert out.read_text(encoding="utf-8") == code

    for token in ("ggplot", "geom_point", "theme", "ggsave", "threshold"):
        assert token in code, f"missing {token}"

    assert "library(ggplot2)" in code
    assert "library(ggrepel)" in code
    assert "library(svglite)" in code
    assert "geom_text_repel" in code
    assert "geom_vline" in code
    assert "geom_hline" in code
    assert 'input_file <- "examples/example_volcano.csv"' in code
    assert '"Up"' in code and '"Down"' in code and '"NS"' in code
    assert "volcano.pdf" in code
    assert "volcano.svg" in code
    assert "volcano.png" in code
    assert "svglite::svglite" in code
    assert "cairo_pdf" in code


def test_all_plot_parameters_come_from_specification() -> None:
    spec = _example_spec()
    code = VolcanoRCodeAgent().generate(spec)

    assert f"point_size <- {spec.geometry.point_size}" in code
    assert f"point_alpha <- {spec.geometry.alpha}" in code
    assert f"threshold_line_width <- {spec.geometry.threshold_line_width}" in code
    assert "linewidth = threshold_line_width" in code
    assert f"width_mm <- {spec.size.width_mm}" in code
    assert f"height_mm <- {spec.size.height_mm}" in code
    assert f"dpi <- {spec.size.dpi}" in code
    assert f"log2fc_threshold <- {spec.plot.statistics.log2fc_threshold}" in code
    assert f"fdr_threshold <- {spec.plot.statistics.fdr_threshold}" in code
    assert f'font_family <- "{spec.font.font_family}"' in code
    assert f"axis_text_size <- {spec.font.axis_text_size}" in code
    assert f'gene_col <- "{spec.plot.data.gene_column}"' in code
    assert f'log2fc_col <- "{spec.plot.data.log2fc_column}"' in code
    assert f'fdr_col <- "{spec.plot.data.significance_column}"' in code
    assert spec.plot.colors.up in code


def test_parameter_change_is_reflected_in_r() -> None:
    spec = _example_spec()
    spec.geometry.point_size = 2.4
    spec.geometry.alpha = 0.4
    spec.size.width_mm = 183
    code = VolcanoRCodeAgent().generate(spec)
    assert "point_size <- 2.4" in code
    assert "point_alpha <- 0.4" in code
    assert "width_mm <- 183" in code


def test_incomplete_spec_is_rejected() -> None:
    spec = FigureSpecification()
    with pytest.raises(ValueError, match="incomplete"):
        VolcanoRCodeAgent().generate(spec)


def test_default_input_file_when_source_missing() -> None:
    spec = _example_spec()
    spec.plot.data.source = None
    code = VolcanoRCodeAgent().generate(spec)
    assert 'input_file <- "input.csv"' in code

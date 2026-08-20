"""Schema tests for FigureSpecification (V0.1 volcano only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import FigureSpecification, FigureType, load_figure_specification

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "schemas" / "examples" / "volcano_nature_rnaseq.json"


def test_example_json_is_valid_and_complete() -> None:
    spec = load_figure_specification(EXAMPLE.read_text(encoding="utf-8"))
    assert spec.figure_type is FigureType.VOLCANO
    assert spec.purpose.value == "publication"
    assert spec.journal_style.value == "Nature"
    assert spec.size.width_mm == 89
    assert spec.size.height_mm == 70
    assert spec.size.dpi == 600
    assert spec.font.font_family == "Arial"
    assert spec.font.axis_text_size == 7
    assert spec.font.axis_title_size == 8
    assert spec.font.legend_size == 7
    assert spec.theme.grid.value == "none"
    assert spec.geometry.point_size == 1.5
    assert spec.geometry.line_width == 0.5
    assert spec.plot.statistics.log2fc_threshold == 1
    assert spec.plot.statistics.fdr_threshold == 0.05
    assert spec.output.pdf and spec.output.svg and spec.output.png
    assert spec.is_complete_for_codegen()


def test_defaults_match_nature_single_column() -> None:
    spec = FigureSpecification()
    dumped = spec.model_dump()
    assert dumped["figure_type"] == FigureType.VOLCANO
    assert spec.size.width_mm == 89
    assert spec.size.dpi == 600
    assert spec.font.axis_text_size == 7
    assert spec.plot.statistics.log2fc_threshold == 1.0
    assert spec.plot.statistics.fdr_threshold == 0.05
    assert not spec.is_complete_for_codegen()
    assert spec.plot.blocking_missing() == [
        "data.log2fc_column",
        "data.significance_column",
        "data.gene_column",
    ]


def test_single_column_default_width() -> None:
    spec = FigureSpecification(size={"column": "single"})
    assert spec.size.width_mm == 89


def test_single_column_keeps_explicit_journal_width() -> None:
    spec = FigureSpecification(size={"column": "single", "width_mm": 85})
    assert spec.size.width_mm == 85


def test_double_column_width() -> None:
    spec = FigureSpecification(size={"column": "double"})
    assert spec.size.width_mm == 183


def test_log2FC_alias_accepted() -> None:
    spec = FigureSpecification(
        plot={"statistics": {"log2FC_threshold": 1.5, "FDR_threshold": 0.01}}
    )
    assert spec.plot.statistics.log2fc_threshold == 1.5
    assert spec.plot.statistics.fdr_threshold == 0.01


def test_publication_rejects_font_below_6pt() -> None:
    with pytest.raises(ValidationError):
        FigureSpecification(purpose="publication", font={"axis_text_size": 5})


def test_internal_allows_smaller_font() -> None:
    spec = FigureSpecification(purpose="internal", font={"axis_text_size": 5})
    assert spec.font.axis_text_size == 5


def test_publication_rejects_thin_line() -> None:
    with pytest.raises(ValidationError):
        FigureSpecification(purpose="publication", geometry={"line_width": 0.2})


def test_v01_rejects_non_volcano_figure_type() -> None:
    with pytest.raises(ValidationError):
        FigureSpecification(figure_type="heatmap")


def test_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        FigureSpecification.model_validate({"figure_type": "volcano", "unknown": 1})


def test_output_requires_at_least_one_format() -> None:
    with pytest.raises(ValidationError):
        FigureSpecification(output={"pdf": False, "svg": False, "png": False})


def test_gene_list_label_requires_genes() -> None:
    with pytest.raises(ValidationError):
        FigureSpecification(
            plot={"labels": {"enabled": True, "mode": "gene_list", "genes": []}}
        )


def test_roundtrip_json(tmp_path: Path) -> None:
    spec = load_figure_specification(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    out = tmp_path / "spec.json"
    out.write_text(spec.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
    again = load_figure_specification(out.read_text(encoding="utf-8"))
    assert again.model_dump() == spec.model_dump()

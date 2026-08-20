"""Figure QC Agent tests. Does not execute R or modify specifications."""

from __future__ import annotations

import json
from pathlib import Path

from qc.figure_qc_agent import FigureQCAgent
from schemas.figure_spec import FigureSpecification, load_figure_specification
from schemas.qc_report import QCStatus

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "schemas" / "examples" / "volcano_nature_rnaseq.json"


def _complete_spec(**kwargs) -> FigureSpecification:
    spec = load_figure_specification(EXAMPLE.read_text(encoding="utf-8"))
    return spec.model_copy(update=kwargs, deep=True)


def _write_figures(directory: Path, *, pdf: bool = True, svg: bool = True, png: bool = True) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if pdf:
        (directory / "volcano.pdf").write_bytes(b"%PDF-1.4\n")
    if svg:
        (directory / "volcano.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    if png:
        (directory / "volcano.png").write_bytes(b"\x89PNG\r\n\x1a\n")


def test_case1_complete_spec_and_files_pass(tmp_path: Path) -> None:
    spec = _complete_spec()
    snapshot = spec.model_dump()
    _write_figures(tmp_path)
    report = FigureQCAgent().check(spec, tmp_path)
    assert report.status is QCStatus.PASS
    assert report.warnings == []
    assert report.checks.file_check == "pass"
    assert report.checks.dimension_check == "pass"
    assert report.checks.resolution_check == "pass"
    assert report.checks.font_check == "pass"
    assert report.checks.parameter_check == "pass"
    assert (tmp_path / "QC_report.json").is_file()
    assert spec.model_dump() == snapshot


def test_case2_missing_svg_warning(tmp_path: Path) -> None:
    spec = _complete_spec()
    _write_figures(tmp_path, svg=False)
    report = FigureQCAgent().check(spec, tmp_path)
    assert report.status is QCStatus.WARNING
    assert report.checks.file_check == "warning"
    assert "Missing SVG output" in report.warnings


def test_case3_font_size_4_warning(tmp_path: Path) -> None:
    spec = _complete_spec(purpose="internal")
    spec.font.axis_text_size = 4
    _write_figures(tmp_path)
    report = FigureQCAgent().check(spec, tmp_path)
    assert report.status is QCStatus.WARNING
    assert report.checks.font_check == "warning"
    assert any("Font size below 6 pt" in item for item in report.warnings)
    assert "Increase axis font size" in report.suggestions


def test_case4_line_width_too_thin_warning(tmp_path: Path) -> None:
    spec = _complete_spec(purpose="internal")
    spec.geometry.line_width = 0.1
    _write_figures(tmp_path)
    report = FigureQCAgent().check(spec, tmp_path)
    assert report.status is QCStatus.WARNING
    assert report.checks.parameter_check == "warning"
    assert any("line_width" in item for item in report.warnings)


def test_case5_dpi_72_warning(tmp_path: Path) -> None:
    spec = _complete_spec()
    spec.size.dpi = 72
    _write_figures(tmp_path)
    report = FigureQCAgent().check(spec, tmp_path)
    assert report.status is QCStatus.WARNING
    assert report.checks.resolution_check == "warning"
    assert any("dpi 72" in item for item in report.warnings)


def test_written_report_roundtrip(tmp_path: Path) -> None:
    spec = _complete_spec()
    _write_figures(tmp_path)
    FigureQCAgent().check(spec, tmp_path)
    payload = json.loads((tmp_path / "QC_report.json").read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["checks"]["file_check"] == "pass"

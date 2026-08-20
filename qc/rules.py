"""Publication QC thresholds and check functions.

All numeric limits live here so figure_qc_agent.py stays orchestration-only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from schemas.figure_spec import ColumnLayout, FigureSpecification, JournalStyle, Purpose

# --- Thresholds (SCI / print-safety heuristics) ---
FONT_MIN_SIZE = 6
MIN_LINE_WIDTH = 0.2
MIN_POINT_SIZE = 0.5
MAX_POINT_SIZE = 5
MIN_ALPHA = 0.2
MIN_DPI = 300
MIN_DPI_PUBLICATION = 600
SIZE_DEVIATION_MAX = 0.20
NATURE_SINGLE_WIDTH_MM = 89.0

OUTPUT_STEMS = ("volcano", "plot")
OUTPUT_SUFFIXES = {
    "pdf": ".pdf",
    "svg": ".svg",
    "png": ".png",
}

_ROOT = Path(__file__).resolve().parents[1]
_JOURNAL_STYLES = _ROOT / "knowledge" / "journals" / "journal_styles.json"


@dataclass
class RuleResult:
    key: str
    status: str
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    detail: str = "pass"


def _merge_status(current: str, incoming: str) -> str:
    rank = {"pass": 0, "warning": 1, "failed": 2}
    return incoming if rank[incoming] > rank[current] else current


def load_journal_profiles() -> dict[str, Any]:
    return json.loads(_JOURNAL_STYLES.read_text(encoding="utf-8"))["journals"]


def recommended_width_mm(spec: FigureSpecification) -> float | None:
    """Official/recommended column width for the spec's journal and layout."""
    if spec.journal_style is JournalStyle.CUSTOM:
        return None
    journals = load_journal_profiles()
    profile = journals.get(spec.journal_style.value)
    if not profile:
        if spec.journal_style is JournalStyle.NATURE:
            return NATURE_SINGLE_WIDTH_MM
        return None
    column = spec.size.column
    if column is ColumnLayout.SINGLE:
        block = profile.get("single_column") or {}
        return float(block["width_mm"]) if "width_mm" in block else None
    if column is ColumnLayout.DOUBLE:
        block = profile.get("double_column") or {}
        return float(block["width_mm"]) if "width_mm" in block else None
    return None


def recommended_max_height_mm(spec: FigureSpecification) -> float | None:
    if spec.journal_style is JournalStyle.CUSTOM:
        return None
    journals = load_journal_profiles()
    profile = journals.get(spec.journal_style.value) or {}
    block = profile.get("max_height_mm") or {}
    if isinstance(block, dict) and "value" in block:
        return float(block["value"])
    return None


def find_output_file(directory: Path, suffix: str) -> Path | None:
    for stem in OUTPUT_STEMS:
        candidate = directory / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    matches = [
        path
        for path in directory.glob(f"*{suffix}")
        if path.is_file() and path.name != "QC_report.json"
    ]
    return matches[0] if matches else None


def check_files(spec: FigureSpecification, output_directory: Path) -> RuleResult:
    result = RuleResult(key="file_check", status="pass", detail="pass")
    if not output_directory.is_dir():
        result.status = "failed"
        result.detail = "failed"
        result.warnings.append("Output directory does not exist")
        result.suggestions.append("Generate figures before running QC.")
        return result

    expected = {
        "pdf": spec.output.pdf,
        "svg": spec.output.svg,
        "png": spec.output.png,
    }
    for kind, required in expected.items():
        if not required:
            continue
        suffix = OUTPUT_SUFFIXES[kind]
        if find_output_file(output_directory, suffix) is None:
            result.status = _merge_status(result.status, "warning")
            result.detail = "warning"
            label = kind.upper()
            result.warnings.append(f"Missing {label} output")
            result.suggestions.append(f"Export {label} ({suffix}) as specified in FigureSpecification.output.")
    if result.status == "pass":
        result.detail = "pass"
    return result


def check_dimensions(spec: FigureSpecification) -> RuleResult:
    result = RuleResult(key="dimension_check", status="pass", detail="pass")
    recommended = recommended_width_mm(spec)
    if recommended and recommended > 0:
        deviation = abs(spec.size.width_mm - recommended) / recommended
        if deviation > SIZE_DEVIATION_MAX:
            result.status = "warning"
            result.detail = "warning"
            result.warnings.append("Figure width differs from recommended journal size")
            result.suggestions.append(
                f"Set size.width_mm to {recommended:g} mm for {spec.journal_style.value} "
                f"{spec.size.column.value} column (deviation {deviation:.0%} > {SIZE_DEVIATION_MAX:.0%})."
            )

    max_height = recommended_max_height_mm(spec)
    if max_height is not None and spec.size.height_mm > max_height:
        result.status = _merge_status(result.status, "warning")
        result.detail = "warning"
        result.warnings.append("Figure height exceeds journal maximum page depth")
        result.suggestions.append(f"Reduce size.height_mm to <= {max_height:g} mm.")
    return result


def check_fonts(spec: FigureSpecification) -> RuleResult:
    result = RuleResult(key="font_check", status="pass", detail="pass")
    sizes = {
        "axis_text_size": spec.font.axis_text_size,
        "axis_title_size": spec.font.axis_title_size,
        "legend_size": spec.font.legend_size,
        "title_size": spec.font.title_size,
    }
    too_small = [name for name, size in sizes.items() if size < FONT_MIN_SIZE]
    if too_small:
        result.status = "warning"
        result.detail = "warning"
        result.warnings.append(
            f"Font size below {FONT_MIN_SIZE} pt: {', '.join(too_small)}"
        )
        result.suggestions.append("Increase axis font size")
    return result


def check_parameters(spec: FigureSpecification) -> RuleResult:
    result = RuleResult(key="parameter_check", status="pass", detail="pass")
    point = spec.geometry.point_size
    if point < MIN_POINT_SIZE:
        result.status = "warning"
        result.warnings.append(f"point_size {point} is below {MIN_POINT_SIZE}")
        result.suggestions.append("Increase geometry.point_size so points remain visible in print.")
    elif point > MAX_POINT_SIZE:
        result.status = "warning"
        result.warnings.append(f"point_size {point} is above {MAX_POINT_SIZE}")
        result.suggestions.append("Reduce geometry.point_size to avoid overplotting.")

    if spec.geometry.line_width < MIN_LINE_WIDTH:
        result.status = "warning"
        result.warnings.append(
            f"line_width {spec.geometry.line_width} is below {MIN_LINE_WIDTH}"
        )
        result.suggestions.append("Increase geometry.line_width to at least 0.3 pt for print.")

    if spec.geometry.alpha < MIN_ALPHA:
        result.status = "warning"
        result.warnings.append(f"alpha {spec.geometry.alpha} is below {MIN_ALPHA}")
        result.suggestions.append("Increase geometry.alpha so points are not nearly invisible.")

    if result.status == "warning":
        result.detail = "warning"
    return result


def check_resolution(spec: FigureSpecification) -> RuleResult:
    result = RuleResult(key="resolution_check", status="pass", detail="pass")
    dpi = spec.size.dpi
    if spec.purpose is Purpose.PUBLICATION and dpi < MIN_DPI_PUBLICATION:
        result.status = "warning"
        result.detail = "warning"
        result.warnings.append(
            f"dpi {dpi} is below {MIN_DPI_PUBLICATION} required for publication raster output"
        )
        result.suggestions.append(f"Set size.dpi to {MIN_DPI_PUBLICATION} (or export vector PDF/SVG).")
    elif dpi < MIN_DPI:
        result.status = "warning"
        result.detail = "warning"
        result.warnings.append(f"dpi {dpi} is below {MIN_DPI}")
        result.suggestions.append(f"Set size.dpi to at least {MIN_DPI}.")
    return result

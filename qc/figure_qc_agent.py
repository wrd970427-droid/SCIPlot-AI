"""Figure Quality Control Agent (V0.1).

Inspects a FigureSpecification and exported files. Does not modify inputs,
regenerate R, call LLMs, or execute code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from qc.rules import (
    check_dimensions,
    check_files,
    check_fonts,
    check_parameters,
    check_resolution,
)
from schemas.figure_spec import FigureSpecification
from schemas.qc_report import QCChecks, QCReport, QCStatus

SpecLike = Union[FigureSpecification, dict]

_STATUS_RANK = {"pass": 0, "warning": 1, "failed": 2}


def _overall(statuses: list[str]) -> QCStatus:
    worst = "pass"
    for status in statuses:
        if _STATUS_RANK[status] > _STATUS_RANK[worst]:
            worst = status
    return QCStatus(worst)


class FigureQCAgent:
    """Independent publication-rule checker for volcano figure outputs."""

    def check(
        self,
        spec: SpecLike,
        output_directory: str | Path,
        *,
        write_report: bool = True,
    ) -> QCReport:
        if not isinstance(spec, FigureSpecification):
            spec = FigureSpecification.model_validate(spec)

        output_dir = Path(output_directory)

        results = [
            check_files(spec, output_dir),
            check_dimensions(spec),
            check_resolution(spec),
            check_fonts(spec),
            check_parameters(spec),
        ]
        by_key = {item.key: item for item in results}
        warnings: list[str] = []
        suggestions: list[str] = []
        for item in results:
            warnings.extend(item.warnings)
            suggestions.extend(item.suggestions)

        report = QCReport(
            status=_overall([item.status for item in results]),
            checks=QCChecks(
                file_check=by_key["file_check"].detail,
                dimension_check=by_key["dimension_check"].detail,
                resolution_check=by_key["resolution_check"].detail,
                font_check=by_key["font_check"].detail,
                parameter_check=by_key["parameter_check"].detail,
            ),
            warnings=warnings,
            suggestions=suggestions,
        )

        if write_report and output_dir.is_dir():
            path = output_dir / "QC_report.json"
            path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report

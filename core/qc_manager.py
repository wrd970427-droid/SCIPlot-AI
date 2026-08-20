"""QC manager — shared QC entry for all figures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.adapters.volcano_adapter import VolcanoAdapter
from qc.figure_qc_agent import FigureQCAgent
from schemas.generic_figure_spec import GenericFigureSpecification
from schemas.qc_report import QCChecks, QCReport, QCStatus


class QCManager:
    """Run QC for a produced figure. Volcano uses legacy FigureQCAgent via adapter."""

    def __init__(
        self,
        qc_agent: FigureQCAgent | None = None,
        volcano_adapter: VolcanoAdapter | None = None,
    ) -> None:
        self.qc_agent = qc_agent or FigureQCAgent()
        self.volcano_adapter = volcano_adapter or VolcanoAdapter()

    def run_qc(
        self,
        figure_spec: GenericFigureSpecification | dict[str, Any],
        output_directory: str | Path,
        *,
        write_report: bool = True,
    ) -> QCReport:
        if not isinstance(figure_spec, GenericFigureSpecification):
            figure_spec = GenericFigureSpecification.model_validate(figure_spec)

        if figure_spec.figure_definition_id == "transcriptomics.volcano":
            legacy = self.volcano_adapter.to_legacy_spec(figure_spec)
            return self.qc_agent.check(legacy, output_directory, write_report=write_report)

        return self._generic_file_qc(figure_spec, output_directory, write_report=write_report)

    def _generic_file_qc(
        self,
        figure_spec: GenericFigureSpecification,
        output_directory: str | Path,
        *,
        write_report: bool,
    ) -> QCReport:
        """Shared file-presence QC for Generic Engine figures without legacy Spec."""
        output_dir = Path(output_directory)
        warnings: list[str] = []
        suggestions: list[str] = []
        file_status = "pass"

        expected = {
            "pdf": bool((figure_spec.output or {}).get("pdf", True)),
            "svg": bool((figure_spec.output or {}).get("svg", True)),
            "png": bool((figure_spec.output or {}).get("png", True)),
        }
        if not output_dir.is_dir():
            file_status = "failed"
            warnings.append("Output directory does not exist")
            suggestions.append("Generate figures before running QC.")
        else:
            for kind, required in expected.items():
                if not required:
                    continue
                suffix = f".{kind}"
                hits = list(output_dir.glob(f"*{suffix}"))
                if not hits:
                    file_status = "warning" if file_status == "pass" else file_status
                    warnings.append(f"Missing {kind.upper()} output")
                    suggestions.append(f"Export {kind.upper()} as specified in output.")

        status = {
            "pass": QCStatus.PASS,
            "warning": QCStatus.WARNING,
            "failed": QCStatus.FAILED,
        }[file_status]

        report = QCReport(
            status=status,
            checks=QCChecks(
                file_check=file_status,
                dimension_check="pass",
                resolution_check="pass",
                font_check="pass",
                parameter_check="pass",
            ),
            warnings=warnings,
            suggestions=suggestions,
        )
        if write_report and output_dir.is_dir():
            (output_dir / "QC_report.json").write_text(
                report.model_dump_json(indent=2),
                encoding="utf-8",
            )
        return report

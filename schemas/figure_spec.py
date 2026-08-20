"""SCIPlot AI — Figure Specification schema (V0.1).

Single source of truth for volcano-plot publication parameters.
Other figure types (heatmap, survival, UMAP, …) will attach as additional
plot payloads later; they are enumerated but not implemented in V0.1.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FigureType(str, Enum):
    """Supported figure types.

    V0.1 implements ``volcano`` only. Remaining members are reserved so the
    protocol can grow without renaming this field.
    """

    VOLCANO = "volcano"
    HEATMAP = "heatmap"
    KAPLAN_MEIER = "kaplan_meier"
    ROC = "roc"
    BOXPLOT = "boxplot"
    VIOLIN = "violin"
    SCATTER = "scatter"
    ENRICHMENT_DOTPLOT = "enrichment_dotplot"
    ONCOPLOT = "oncoplot"
    UMAP = "umap"


class Purpose(str, Enum):
    INTERNAL = "internal"
    PUBLICATION = "publication"


class JournalStyle(str, Enum):
    NATURE = "Nature"
    CELL = "Cell"
    SCIENCE = "Science"
    NATURE_COMMUNICATIONS = "Nature Communications"
    CANCER_CELL = "Cancer Cell"
    MICROBIOME = "Microbiome"
    MSYSTEMS = "mSystems"
    CUSTOM = "Custom"


class ColumnLayout(str, Enum):
    SINGLE = "single"
    DOUBLE = "double"
    CUSTOM = "custom"


class SignificanceMetric(str, Enum):
    FDR = "fdr"
    PVALUE = "pvalue"


class GridStyle(str, Enum):
    NONE = "none"
    MAJOR = "major"
    BOTH = "both"


class BorderStyle(str, Enum):
    NONE = "none"
    PANEL = "panel"
    FULL = "full"  # alias for a full rectangular panel border


# Nature single-column defaults (mm / pt).
NATURE_SINGLE_WIDTH_MM = 89.0
NATURE_DOUBLE_WIDTH_MM = 183.0
DEFAULT_HEIGHT_MM = 70.0
DEFAULT_DPI = 600
MIN_FONT_PT_PUBLICATION = 6.0
MIN_LINE_WIDTH_PUBLICATION = 0.3


class SizeSpec(BaseModel):
    """Physical size and raster resolution.

    ``column=single/double`` only fills width when the caller omits ``width_mm``.
    Journal profiles (Cell 85 mm, Science 57 mm, …) must be able to keep their
    official widths; those values are applied by the Requirement Agent.
    """

    model_config = ConfigDict(extra="forbid")

    column: ColumnLayout = ColumnLayout.SINGLE
    width_mm: float = Field(default=NATURE_SINGLE_WIDTH_MM, gt=0)
    height_mm: float = Field(default=DEFAULT_HEIGHT_MM, gt=0)
    dpi: int = Field(default=DEFAULT_DPI, ge=72, le=1200)

    @model_validator(mode="before")
    @classmethod
    def _default_width_from_column(cls, data):
        if not isinstance(data, dict):
            return data
        column = data.get("column", "single")
        if isinstance(column, ColumnLayout):
            column = column.value
        if "width_mm" not in data or data.get("width_mm") is None:
            if column == "double":
                data = {**data, "width_mm": NATURE_DOUBLE_WIDTH_MM}
            elif column == "single":
                data = {**data, "width_mm": NATURE_SINGLE_WIDTH_MM}
        return data


class FontSpec(BaseModel):
    """Type sizes in points (pt). Field names match the product spec."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    font_family: str = "Arial"
    axis_text_size: float = Field(default=7, ge=1, le=24)
    axis_title_size: float = Field(default=8, ge=1, le=24)
    legend_size: float = Field(default=7, ge=1, le=24)
    title_size: float = Field(default=8, ge=1, le=24)


class ThemeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    background: Literal["white", "transparent"] = "white"
    grid: GridStyle = GridStyle.NONE
    border: BorderStyle = BorderStyle.NONE
    legend_position: Literal["right", "left", "bottom", "top", "none"] = "right"


class GeometrySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    point_size: float = Field(default=1.5, gt=0, le=10)
    line_width: float = Field(
        default=0.5,
        gt=0,
        le=5,
        description="Axis / panel border stroke (ggplot axis.line, panel.border).",
    )
    threshold_line_width: float = Field(
        default=0.35,
        gt=0,
        le=5,
        description="Internal dashed threshold lines (geom_hline / geom_vline).",
    )
    alpha: float = Field(default=0.7, ge=0, le=1)


class OutputSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pdf: bool = True
    svg: bool = True
    png: bool = True

    @model_validator(mode="after")
    def _at_least_one_format(self) -> "OutputSpec":
        if not (self.pdf or self.svg or self.png):
            raise ValueError("At least one output format (pdf/svg/png) must be enabled.")
        return self


class VolcanoColors(BaseModel):
    """Up / down / not-significant colors. Overridable; defaults are Nature-like."""

    model_config = ConfigDict(extra="forbid")

    up: str = "#E64B35"
    down: str = "#4DBBD5"
    ns: str = "#B0B0B0"


class VolcanoLabelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    mode: Literal["none", "top_n", "gene_list"] = "none"
    top_n: int = Field(default=10, ge=1, le=200)
    genes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _mode_consistency(self) -> "VolcanoLabelSpec":
        if not self.enabled:
            self.mode = "none"
            return self
        if self.mode == "none":
            self.mode = "top_n"
        if self.mode == "gene_list" and not self.genes:
            raise ValueError("label.mode='gene_list' requires a non-empty genes list.")
        return self


class VolcanoStatistics(BaseModel):
    """Significance cutoffs used to color and (optionally) label points."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    log2fc_threshold: float = Field(default=1.0, ge=0, alias="log2FC_threshold")
    fdr_threshold: float = Field(default=0.05, gt=0, le=1, alias="FDR_threshold")
    significance_metric: SignificanceMetric = SignificanceMetric.FDR


class VolcanoDataSpec(BaseModel):
    """Column mapping. None means the Requirement Agent has not filled it yet."""

    model_config = ConfigDict(extra="forbid")

    source: Optional[str] = Field(
        default=None,
        description="Path or upload id of the differential-expression table.",
    )
    log2fc_column: Optional[str] = Field(default=None, description="Column name for log2 fold change.")
    significance_column: Optional[str] = Field(
        default=None,
        description="Column name for p-value or FDR.",
    )
    gene_column: Optional[str] = Field(default=None, description="Column name for gene symbols/IDs.")


class VolcanoPlotSpec(BaseModel):
    """Volcano-specific payload. Other figure types will get sibling models."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    figure_type: Literal["volcano"] = "volcano"
    data: VolcanoDataSpec = Field(default_factory=VolcanoDataSpec)
    statistics: VolcanoStatistics = Field(default_factory=VolcanoStatistics)
    labels: VolcanoLabelSpec = Field(default_factory=VolcanoLabelSpec)
    colors: VolcanoColors = Field(default_factory=VolcanoColors)

    def blocking_missing(self) -> list[str]:
        """Return data fields that must be known before R code generation."""
        missing: list[str] = []
        if not self.data.log2fc_column:
            missing.append("data.log2fc_column")
        if not self.data.significance_column:
            missing.append("data.significance_column")
        if not self.data.gene_column:
            missing.append("data.gene_column")
        return missing


class FigureSpecification(BaseModel):
    """Unified Figure Specification protocol (V0.1: volcano only).

    All drawing parameters consumed by the R Code Agent MUST come from this
    object. Do not hard-code sizes, fonts, or thresholds in code generators.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    spec_version: str = "0.1.0"
    figure_type: FigureType = FigureType.VOLCANO
    purpose: Purpose = Purpose.PUBLICATION
    journal_style: JournalStyle = JournalStyle.NATURE
    size: SizeSpec = Field(default_factory=SizeSpec)
    font: FontSpec = Field(default_factory=FontSpec)
    theme: ThemeSpec = Field(default_factory=ThemeSpec)
    geometry: GeometrySpec = Field(default_factory=GeometrySpec)
    output: OutputSpec = Field(default_factory=OutputSpec)
    plot: VolcanoPlotSpec = Field(default_factory=VolcanoPlotSpec)

    @field_validator("spec_version")
    @classmethod
    def _version_semver(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("spec_version must be a three-part numeric version, e.g. '0.1.0'.")
        return value

    @model_validator(mode="after")
    def _v01_volcano_only(self) -> "FigureSpecification":
        if self.figure_type is not FigureType.VOLCANO:
            raise ValueError(
                "SCIPlot AI V0.1 only supports figure_type='volcano'. "
                f"Received '{self.figure_type.value}'."
            )
        if self.plot.figure_type != "volcano":
            raise ValueError("plot.figure_type must be 'volcano' in V0.1.")
        return self

    @model_validator(mode="after")
    def _publication_constraints(self) -> "FigureSpecification":
        if self.purpose is not Purpose.PUBLICATION:
            return self

        font_fields = {
            "axis_text_size": self.font.axis_text_size,
            "axis_title_size": self.font.axis_title_size,
            "legend_size": self.font.legend_size,
            "title_size": self.font.title_size,
        }
        too_small = [name for name, size in font_fields.items() if size < MIN_FONT_PT_PUBLICATION]
        if too_small:
            raise ValueError(
                f"Publication figures require font size >= {MIN_FONT_PT_PUBLICATION} pt; "
                f"too small: {too_small}."
            )
        if self.geometry.line_width < MIN_LINE_WIDTH_PUBLICATION:
            raise ValueError(
                f"Publication figures require line_width >= {MIN_LINE_WIDTH_PUBLICATION}."
            )
        return self

    def is_complete_for_codegen(self) -> bool:
        """True when blocking volcano data columns are filled."""
        return not self.plot.blocking_missing()


def load_figure_specification(data: dict | str) -> FigureSpecification:
    """Parse a dict or JSON string into a validated FigureSpecification."""
    if isinstance(data, str):
        return FigureSpecification.model_validate_json(data)
    return FigureSpecification.model_validate(data)


# Discriminator alias for later Union[VolcanoPlotSpec, HeatmapPlotSpec, ...].
PlotSpec = Annotated[VolcanoPlotSpec, Field(discriminator="figure_type")]

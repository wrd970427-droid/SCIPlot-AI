"""Build GenericFigureSpecification from RequirementEngine output."""

from __future__ import annotations

from typing import Any

from core.requirement_engine import GenericRequirementResponse, GenericRequirementStatus
from schemas.figure_definition import FigureDefinition
from schemas.generic_figure_spec import GenericFigureSpecification


class SpecificationBuilder:
    """RequirementResponse → GenericFigureSpecification (no NL, no R)."""

    def build(
        self,
        definition: FigureDefinition,
        requirement: GenericRequirementResponse,
        *,
        data_source: str | None = None,
        extra_style: dict[str, Any] | None = None,
    ) -> GenericFigureSpecification:
        if requirement.status is not GenericRequirementStatus.READY:
            raise ValueError("Cannot build specification while requirement status is not ready")

        mapping = {
            key: str(value)
            for key, value in requirement.known_mapping.items()
            if key != "data_source" and value is not None
        }
        source = data_source or requirement.known_mapping.get("data_source")
        style = dict(requirement.style_profile)
        if extra_style:
            style.update(extra_style)

        qc_requirement = {
            "min_font_pt": 6,
            "min_line_width": 0.3,
            "require_vector": True,
        }

        return GenericFigureSpecification(
            figure_definition_id=definition.id,
            data_schema_id=definition.data_schema_id,
            data_mapping=mapping,
            data_source=str(source) if source else None,
            statistics=dict(requirement.statistics),
            visual_parameters=dict(requirement.visual_parameters),
            style_profile=style,
            output={"pdf": True, "svg": True, "png": True},
            qc_requirement=qc_requirement,
        )

"""Apply FigureModification patches onto a Spec (design params only).

Works on both:
- legacy volcano FigureSpecification
- GenericFigureSpecification

Logical parameter names are shared. Physical paths depend on Spec shape.
"""

from __future__ import annotations

import copy
from typing import Any

from schemas.figure_modification import FigureModification
from schemas.figure_spec import (
    BorderStyle,
    FigureSpecification,
    MIN_FONT_PT_PUBLICATION,
    MIN_LINE_WIDTH_PUBLICATION,
    Purpose,
)
from schemas.generic_figure_spec import GenericFigureSpecification

# Logical names → volcano FigureSpecification paths.
PARAMETER_PATHS: dict[str, list[str]] = {
    "font_size": [
        "font.axis_text_size",
        "font.axis_title_size",
        "font.legend_size",
        "font.title_size",
    ],
    "point_size": ["geometry.point_size"],
    "line_width": ["geometry.line_width"],
    "threshold_line_width": ["geometry.threshold_line_width"],
    "alpha": ["geometry.alpha"],
    "width_mm": ["size.width_mm"],
    "height_mm": ["size.height_mm"],
    "panel_border": ["theme.border"],
    "border": ["theme.border"],
    "legend_position": ["theme.legend_position"],
    "theme.grid": ["theme.grid"],
    "grid": ["theme.grid"],
    "journal_style": ["journal_style"],
    "colors": ["plot.colors.up", "plot.colors.down", "plot.colors.ns"],
    "point_color": ["plot.colors.up"],
}

GENERIC_PARAMETER_PATHS: dict[str, list[str]] = {
    "font_size": ["visual_parameters.font_size"],
    "point_size": ["visual_parameters.point_size"],
    "size_max": ["visual_parameters.size_max"],
    "line_width": ["visual_parameters.line_width"],
    "threshold_line_width": ["visual_parameters.threshold_line_width"],
    "alpha": ["visual_parameters.alpha"],
    "width_mm": ["visual_parameters.width_mm"],
    "height_mm": ["visual_parameters.height_mm"],
    "panel_border": ["visual_parameters.border"],
    "border": ["visual_parameters.border"],
    "legend_position": ["visual_parameters.legend_position"],
    "theme.grid": ["visual_parameters.grid"],
    "grid": ["visual_parameters.grid"],
    "journal_style": ["style_profile.journal_style"],
    "colors": ["visual_parameters.point_color"],
    "point_color": ["visual_parameters.point_color"],
}

VOLCANO_PATH_TO_GENERIC: dict[str, str] = {
    "font.axis_text_size": "visual_parameters.font_size",
    "font.axis_title_size": "visual_parameters.font_size",
    "font.legend_size": "visual_parameters.font_size",
    "font.title_size": "visual_parameters.font_size",
    "geometry.point_size": "visual_parameters.point_size",
    "geometry.line_width": "visual_parameters.line_width",
    "geometry.threshold_line_width": "visual_parameters.threshold_line_width",
    "geometry.alpha": "visual_parameters.alpha",
    "size.width_mm": "visual_parameters.width_mm",
    "size.height_mm": "visual_parameters.height_mm",
    "size.column": "visual_parameters.column",
    "theme.border": "visual_parameters.border",
    "theme.legend_position": "visual_parameters.legend_position",
    "theme.grid": "visual_parameters.grid",
    "journal_style": "style_profile.journal_style",
    "plot.colors.up": "visual_parameters.point_color",
    "plot.colors.down": "visual_parameters.point_color",
    "plot.colors.ns": "visual_parameters.neutral_color",
}

FORBIDDEN_PREFIXES_VOLCANO = (
    "figure_type",
    "plot.data",
    "plot.statistics",
)

FORBIDDEN_PREFIXES_GENERIC = (
    "figure_definition_id",
    "data_schema_id",
    "data_mapping",
    "statistics",
    "data_source",
)

NAMED_COLORS: dict[str, str] = {
    "blue": "#2E86AB",
    "蓝色": "#2E86AB",
    "蓝": "#2E86AB",
    "red": "#E64B35",
    "红色": "#E64B35",
    "红": "#E64B35",
    "green": "#00A087",
    "绿色": "#00A087",
    "绿": "#00A087",
    "black": "#000000",
    "黑色": "#000000",
    "黑": "#000000",
    "orange": "#E18727",
    "橙色": "#E18727",
    "灰": "#7F7F7F",
    "灰色": "#7F7F7F",
    "gray": "#7F7F7F",
    "grey": "#7F7F7F",
    "purple": "#7876B1",
    "紫色": "#7876B1",
}


def resolve_named_color(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.startswith("#") and len(text) in {4, 7}:
        return text
    return NAMED_COLORS.get(text.lower()) or NAMED_COLORS.get(text)


def is_generic_spec(payload: dict[str, Any] | Any) -> bool:
    if isinstance(payload, GenericFigureSpecification):
        return True
    if isinstance(payload, dict):
        return bool(payload.get("figure_definition_id"))
    return False


class ParameterMapper:
    """Patch Spec paths. Rejects analysis / data / figure-type changes."""

    def apply(
        self,
        spec: FigureSpecification | GenericFigureSpecification | dict[str, Any],
        modifications: list[FigureModification],
        *,
        palettes: dict[str, dict[str, str]] | None = None,
    ) -> tuple[FigureSpecification | GenericFigureSpecification, list[FigureModification]]:
        payload = self._as_payload(spec)
        generic = is_generic_spec(payload)
        applied: list[FigureModification] = []
        palettes = palettes or {}

        for mod in modifications:
            name = mod.target_parameter
            if name == "nature_single_column" and isinstance(mod.new_value, dict):
                for path, value in mod.new_value.items():
                    filled = self._apply_path(
                        payload, path, value, reason=mod.reason, confidence=mod.confidence
                    )
                    applied.extend(filled)
                continue
            if name == "colors" and isinstance(mod.new_value, str):
                named = resolve_named_color(mod.new_value)
                if named:
                    path = (
                        "visual_parameters.point_color"
                        if generic
                        else "plot.colors.up"
                    )
                    filled = self._apply_path(
                        payload,
                        path,
                        named,
                        reason=mod.reason or f"Set point color to {mod.new_value}",
                        confidence=mod.confidence,
                    )
                    applied.extend(filled)
                    continue
                palette = palettes.get(mod.new_value) or (
                    palettes.get("Nature") if mod.new_value == "npg" else None
                )
                if palette is None:
                    raise ValueError(f"Unknown color or palette: {mod.new_value}")
                if generic:
                    filled = self._apply_path(
                        payload,
                        "visual_parameters.point_color",
                        palette.get("up", "#3C5488"),
                        reason=mod.reason or f"Apply {mod.new_value} palette",
                        confidence=mod.confidence,
                    )
                    applied.extend(filled)
                    continue
                for key, color in palette.items():
                    filled = self._apply_path(
                        payload,
                        f"plot.colors.{key}",
                        color,
                        reason=mod.reason or f"Apply {mod.new_value} palette",
                        confidence=mod.confidence,
                    )
                    applied.extend(filled)
                continue

            if name in {"point_color", "visual_parameters.point_color"} or (
                isinstance(mod.new_value, str)
                and name.endswith("point_color")
            ):
                named = resolve_named_color(mod.new_value)
                if named is not None:
                    mod = mod.model_copy(update={"new_value": named})
                    name = mod.target_parameter

            paths = self.paths_for(name, payload)
            if not paths:
                raise ValueError(f"Unknown refinement parameter: {name}")

            if (
                name == "font_size"
                and mod.old_value is not None
                and isinstance(mod.new_value, (int, float))
            ):
                delta = float(mod.new_value) - float(mod.old_value)
                for path in paths:
                    current = self.read_path(payload, path)
                    if current is None:
                        current = float(mod.new_value)
                    filled = self._apply_path(
                        payload,
                        path,
                        float(current) + delta,
                        reason=mod.reason,
                        confidence=mod.confidence,
                    )
                    applied.extend(filled)
                continue

            for path in paths:
                filled = self._apply_path(
                    payload,
                    path,
                    mod.new_value,
                    reason=mod.reason,
                    confidence=mod.confidence,
                )
                applied.extend(filled)

        updated: FigureSpecification | GenericFigureSpecification
        if generic:
            updated = GenericFigureSpecification.model_validate(payload)
        else:
            updated = FigureSpecification.model_validate(payload)
        return updated, applied

    def paths_for(self, name: str, payload: dict[str, Any]) -> list[str]:
        if is_generic_spec(payload):
            if name in GENERIC_PARAMETER_PATHS:
                return list(GENERIC_PARAMETER_PATHS[name])
            if name in VOLCANO_PATH_TO_GENERIC:
                return [VOLCANO_PATH_TO_GENERIC[name]]
            if "." in name:
                return [VOLCANO_PATH_TO_GENERIC.get(name, name)]
            return []
        return list(PARAMETER_PATHS.get(name, [name] if "." in name else []))

    def compute_new_value(self, current: Any, operation: str, value: Any) -> Any:
        if operation == "set" or operation == "preset" or operation == "palette":
            return value
        if operation == "increase":
            return float(current) + float(value)
        if operation == "decrease":
            return float(current) - float(value)
        if operation == "multiply":
            return float(current) * float(value)
        raise ValueError(f"Unsupported operation: {operation}")

    def read_path(self, payload: dict[str, Any], path: str) -> Any:
        path = self._physical_path(payload, path)
        node: Any = payload
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    def _physical_path(self, payload: dict[str, Any], path: str) -> str:
        if is_generic_spec(payload):
            return VOLCANO_PATH_TO_GENERIC.get(path, path)
        return path

    def _apply_path(
        self,
        payload: dict[str, Any],
        path: str,
        new_value: Any,
        *,
        reason: str,
        confidence: float,
        relative_op: str | None = None,
    ) -> list[FigureModification]:
        path = self._physical_path(payload, path)
        self._assert_allowed(path, payload)
        old = self.read_path(payload, path)
        value = new_value
        if path.endswith("border") and isinstance(value, str):
            token = value.lower()
            if token in {"full", "panel", "black"}:
                value = BorderStyle.FULL.value if token in {"full", "black"} else BorderStyle.PANEL.value
            elif token in {"none", "off"}:
                value = BorderStyle.NONE.value
        if "color" in path.lower() and isinstance(value, str):
            named = resolve_named_color(value)
            if named is not None:
                value = named
        if self._is_font_path(path):
            value = self._clamp_font(payload, float(value))
        if path in {"geometry.line_width", "visual_parameters.line_width"}:
            value = self._clamp_line(payload, float(value))
        if path in {"geometry.threshold_line_width", "visual_parameters.threshold_line_width"}:
            value = max(0.1, min(5.0, float(value)))
        if path in {"geometry.point_size", "visual_parameters.point_size"}:
            value = max(0.2, min(10.0, float(value)))
        if path == "visual_parameters.size_max":
            value = max(1.0, min(20.0, float(value)))
        if path.endswith("width_mm"):
            value = float(value)

        self._set_path(payload, path, value)
        return [
            FigureModification(
                target_parameter=path,
                old_value=old,
                new_value=value,
                reason=reason,
                confidence=confidence,
            )
        ]

    def _set_path(self, payload: dict[str, Any], path: str, value: Any) -> None:
        parts = path.split(".")
        node = payload
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value

    def _assert_allowed(self, path: str, payload: dict[str, Any]) -> None:
        prefixes = FORBIDDEN_PREFIXES_GENERIC if is_generic_spec(payload) else FORBIDDEN_PREFIXES_VOLCANO
        for prefix in prefixes:
            if path == prefix or path.startswith(prefix + "."):
                raise ValueError(f"Refinement cannot modify analysis parameter: {path}")

    @staticmethod
    def _is_font_path(path: str) -> bool:
        if path == "visual_parameters.font_size":
            return True
        return path.startswith("font.") and path.endswith("_size")

    def _clamp_font(self, payload: dict[str, Any], size: float) -> float:
        purpose = payload.get("purpose")
        if purpose is None:
            purpose = (payload.get("style_profile") or {}).get("purpose", Purpose.PUBLICATION.value)
        if purpose == Purpose.PUBLICATION.value:
            return max(MIN_FONT_PT_PUBLICATION, min(24.0, size))
        return max(1.0, min(24.0, size))

    def _clamp_line(self, payload: dict[str, Any], width: float) -> float:
        purpose = payload.get("purpose")
        if purpose is None:
            purpose = (payload.get("style_profile") or {}).get("purpose", Purpose.PUBLICATION.value)
        if purpose == Purpose.PUBLICATION.value:
            return max(MIN_LINE_WIDTH_PUBLICATION, min(5.0, width))
        return max(0.1, min(5.0, width))

    @staticmethod
    def _as_payload(
        spec: FigureSpecification | GenericFigureSpecification | dict[str, Any],
    ) -> dict[str, Any]:
        if isinstance(spec, (FigureSpecification, GenericFigureSpecification)):
            return spec.model_dump(mode="python", by_alias=True)
        return copy.deepcopy(spec)

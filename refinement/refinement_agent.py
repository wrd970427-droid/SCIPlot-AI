"""Figure Refinement Agent — NL design tweaks → Spec patches → history.

Priority:
1) Learned user corrections
2) LLM NLU (optional) with ggplot2 disambiguation
3) Keyword / local paraphrase rules

Never regenerates full Spec; never changes figure type / statistics / data.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from llm.intent_parser import extract_json_object
from llm.llm_client import LLMClient, LLMError
from refinement.parameter_mapper import PARAMETER_PATHS, ParameterMapper, resolve_named_color
from refinement.prompt_templates import REFINEMENT_SYSTEM_PROMPT, refinement_user_message
from refinement.rule_learner import RuleLearner
from schemas.figure_modification import FigureModification, ModificationRequest
from schemas.figure_spec import FigureSpecification
from schemas.generic_figure_spec import GenericFigureSpecification
from schemas.spec_history import SpecHistory

logger = logging.getLogger("sciplot.refinement")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = ROOT / "knowledge" / "refinement_rules.json"

ALLOWED_PARAMETERS = set(PARAMETER_PATHS) | {
    "nature_single_column",
    "colors",
    "point_color",
    "size_max",
    "journal_style",
    "theme.grid",
    "outer_thick_inner_thin",
    "threshold_line_width",
}
ALLOWED_OPERATIONS = {"increase", "decrease", "multiply", "set", "preset", "palette"}

# Offline NLU paraphrases → rule id. Order matters for disambiguation.
LOCAL_PARAPHRASE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(字体|文字|字号|字).{0,6}(增大|加大|放大|大一点|更大)|加大字体|放大字体"), "font_larger"),
    (re.compile(r"(字体|文字|字号|字).{0,6}(减小|缩小|小一点|更小)|缩小字体"), "font_smaller"),
    (re.compile(r"(图片|图|figure|width).{0,6}(变宽|加宽|更宽)|变宽|加宽|宽一点"), "width_wider"),
    (re.compile(r"(图片|图|figure|width).{0,6}(变窄|更窄)|变窄|窄一点"), "width_narrower"),
    (re.compile(r"(点).{0,12}(小一点|更小|减小|缩小)|缩小点|点的大小.{0,6}小"), "points_smaller"),
    (re.compile(r"(点).{0,12}(大一点|更大|增大|放大)|放大点|点的大小.{0,6}大"), "points_larger"),
    # Axis thicken BEFORE generic border — ggplot2 axis.line, not panel.border.
    (re.compile(r"只加粗外边框.{0,12}虚线变细|外边框加粗.{0,8}虚线变细|轴线加粗.{0,8}虚线变细"), "outer_thick_inner_thin"),
    (re.compile(r"(加粗|加粗边框|边框加粗|轴线加粗|坐标轴加粗|线粗一点|轴线粗|加粗外边框|外边框加粗)"), "thicken_axis_lines"),
    (re.compile(r"(轴线细|边框细|thinner axis)"), "thin_axis_lines"),
    (re.compile(r"(虚线变细|内部虚线|阈值线变细|参考线变细|dashed thinner|threshold thinner)", re.I), "thin_threshold_lines"),
    (re.compile(r"(虚线加粗|阈值线加粗|参考线加粗|threshold thicker)", re.I), "thicken_threshold_lines"),
    (re.compile(r"(全边框|四周加边框|四周加黑色边框|增加四周边框|加方框|改成全边框|boxed|full border|panel\s*border)", re.I), "add_border"),
    (re.compile(r"(去掉边框|不要边框|无边框|去掉全边框|不要全边框|no\s*border)", re.I), "remove_border"),
    (re.compile(r"(加网格|显示网格|打开网格|show\s*grid|major\s*grid)", re.I), "show_major_grid"),
    (re.compile(r"(去掉网格|不要网格|隐藏网格|no\s*grid|hide\s*grid)", re.I), "hide_grid"),
    (re.compile(r"nature.{0,8}单栏|改成nature单栏", re.I), "nature_single"),
    (re.compile(r"(nature|Nature).{0,8}(颜色|配色|风格)|颜色换成nature", re.I), "nature_colors"),
    (re.compile(r"图例.{0,6}(下面|下方|底部)|legend.{0,6}bottom", re.I), "legend_bottom"),
    (re.compile(r"图例.{0,6}(右边|右侧)|legend.{0,6}right", re.I), "legend_right"),
    (re.compile(r"图例.{0,6}(上面|上方|顶部)|legend.{0,6}top", re.I), "legend_top"),
]

_COLOR_TOKEN_RE = re.compile(
    r"(蓝色?|红色?|绿色?|黑色?|橙色?|紫色?|灰色?|blue|red|green|black|orange|purple|gr[ae]y)",
    re.I,
)
_POINT_COLOR_RE = re.compile(
    r"(?:点的?颜色|点色|颜色).{0,20}"
    + _COLOR_TOKEN_RE.pattern
    + r"|(?:改成|修改为|变为|换成|设置为)\s*"
    + _COLOR_TOKEN_RE.pattern,
    re.I,
)


class RefinementResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    message: str = ""
    source: str = "rules"
    modifications: list[FigureModification] = Field(default_factory=list)
    previous_spec: Optional[dict[str, Any]] = None
    updated_spec: Optional[dict[str, Any]] = None
    previous_version: int = 0
    current_version: int = 0
    history: Optional[dict[str, Any]] = None


class RefinementAgent:
    """Parse user feedback and patch design parameters on the current Spec."""

    def __init__(
        self,
        rules_path: str | Path | None = None,
        mapper: ParameterMapper | None = None,
        llm_client: LLMClient | None = None,
        learner: RuleLearner | None = None,
        *,
        llm_enabled: bool | None = None,
    ) -> None:
        path = Path(rules_path) if rules_path else DEFAULT_RULES
        self.rules_doc = json.loads(path.read_text(encoding="utf-8"))
        self.rules: list[dict[str, Any]] = list(self.rules_doc.get("rules", []))
        self.palettes: dict[str, dict[str, str]] = dict(self.rules_doc.get("palettes", {}))
        self.mapper = mapper or ParameterMapper()
        self.learner = learner or RuleLearner()
        self.llm_client = llm_client if llm_client is not None else LLMClient()
        self.llm_enabled = self.llm_client.available if llm_enabled is None else llm_enabled

    def parse(self, user_request: str, current_spec: FigureSpecification | dict[str, Any]) -> ModificationRequest:
        text = (user_request or "").strip()
        if not text:
            return ModificationRequest(unmatched=True, message="Empty modification request")

        payload = (
            current_spec.model_dump(mode="python", by_alias=True)
            if isinstance(current_spec, (FigureSpecification, GenericFigureSpecification))
            else dict(current_spec)
        )
        forbidden = self._negation_forbidden(text)

        # Color requests before LLM — avoid palette/hex hallucinations.
        color_req = self._parse_point_color_request(text, payload)
        if color_req is not None:
            return color_req

        # 1) Learned corrections first.
        learned = self.learner.match(text)
        if learned and learned.get("operations"):
            mods = self._ops_dicts_to_modifications(learned["operations"], payload, text)
            mods = self._filter_forbidden(mods, forbidden | set(learned.get("forbidden") or []))
            if mods:
                return ModificationRequest(modifications=mods, message="ok:learned")

        # 2) LLM NLU.
        if self.llm_enabled:
            try:
                llm_req = self._parse_llm(text, payload)
                if not llm_req.unmatched and llm_req.modifications:
                    llm_req.modifications = self._filter_forbidden(llm_req.modifications, forbidden)
                    if llm_req.modifications:
                        llm_req.message = "ok:llm"
                        return llm_req
            except (LLMError, ValueError, json.JSONDecodeError, ValidationError, KeyError, TypeError) as exc:
                logger.warning("LLM refinement parse failed; falling back to rules: %s", exc)

        # 3) Rules + local paraphrases.
        rules_req = self._parse_rules(text, payload, forbidden=forbidden)
        if not rules_req.unmatched:
            rules_req.message = "ok:rules"
        return rules_req

    def refine(
        self,
        current_spec: FigureSpecification | dict[str, Any],
        user_request: str,
        history: SpecHistory | None = None,
    ) -> RefinementResult:
        """Parse → patch Spec → append SpecHistory version → maybe learn."""
        spec = current_spec
        if isinstance(current_spec, dict):
            spec = current_spec
        previous = (
            spec.model_dump(mode="json", by_alias=True)
            if isinstance(spec, (FigureSpecification, GenericFigureSpecification))
            else dict(spec)
        )
        request = self.parse(user_request, spec)
        source = "rules"
        if request.message.endswith(":llm"):
            source = "llm"
        elif request.message.endswith(":learned"):
            source = "learned"

        if request.unmatched or not request.modifications:
            return RefinementResult(
                status="unmatched",
                message=request.message or "No matching refinement",
                source=source,
                previous_spec=previous,
                updated_spec=previous,
                previous_version=history.current_version if history else 1,
                current_version=history.current_version if history else 1,
                history=history.summary() if history else None,
            )

        updated, applied = self.mapper.apply(
            spec,
            self._retarget_point_size_for_bubbles(request.modifications, previous),
            palettes=self.palettes,
        )
        updated_dump = updated.model_dump(mode="json", by_alias=True)

        if history is None:
            history = SpecHistory.from_initial(previous, note="initial")
        previous_version = history.current_version
        history.push(
            updated,
            modifications=applied,
            note=user_request.strip(),
        )

        # Learn correction phrasing for next time (design ops only; no data).
        try:
            self.learner.learn_from_request(
                user_request,
                [
                    {
                        "parameter": m.target_parameter if m.target_parameter in ALLOWED_PARAMETERS else self._logical_name(m),
                        "operation": "set",
                        "value": m.new_value,
                        "confidence": m.confidence,
                    }
                    for m in request.modifications
                ],
                note=f"auto from {source}",
            )
        except Exception as exc:  # noqa: BLE001 — learning must not break refine
            logger.warning("Rule learning skipped: %s", exc)

        return RefinementResult(
            status="ready",
            message="Spec refined",
            source=source,
            modifications=applied,
            previous_spec=previous,
            updated_spec=updated_dump,
            previous_version=previous_version,
            current_version=history.current_version,
            history=history.summary(),
        )

    def _parse_point_color_request(
        self,
        text: str,
        payload: dict[str, Any],
    ) -> ModificationRequest | None:
        if "nature" in text.lower() and ("颜色" in text or "配色" in text or "color" in text.lower()):
            return None
        match = _POINT_COLOR_RE.search(text)
        if not match:
            return None
        token = None
        for group in match.groups():
            if group:
                token = group
                break
        if token is None:
            color_hit = _COLOR_TOKEN_RE.search(match.group(0))
            token = color_hit.group(1) if color_hit else None
        if not token:
            return None
        named = resolve_named_color(token) or resolve_named_color(token.rstrip("色"))
        if not named:
            return None
        parameter = "point_color"
        paths = self.mapper.paths_for(parameter, payload)
        ref_path = paths[0] if paths else "visual_parameters.point_color"
        current = self.mapper.read_path(payload, ref_path)
        return ModificationRequest(
            modifications=[
                FigureModification(
                    target_parameter=parameter,
                    old_value=current,
                    new_value=named,
                    reason=f"User requested point color: {token}",
                    confidence=0.96,
                )
            ],
            message="ok:rules",
        )

    def _retarget_point_size_for_bubbles(
        self,
        modifications: list[FigureModification],
        payload: dict[str, Any],
    ) -> list[FigureModification]:
        """When size is mapped to a data column, '点小一点' must shrink scale_size_area."""
        if not (payload.get("data_mapping") or {}).get("size"):
            return modifications
        visual = payload.get("visual_parameters") or {}
        current_max = float(visual.get("size_max", 6.0))
        remapped: list[FigureModification] = []
        for mod in modifications:
            name = mod.target_parameter
            if name not in {"point_size", "visual_parameters.point_size"}:
                remapped.append(mod)
                continue
            if mod.old_value is not None and isinstance(mod.new_value, (int, float)):
                delta = float(mod.new_value) - float(mod.old_value)
                new_max = max(1.0, min(20.0, current_max + delta * 3.0))
            elif isinstance(mod.new_value, (int, float)):
                value = float(mod.new_value)
                new_max = value if value >= 2.0 else max(1.0, value * 3.0)
            else:
                remapped.append(mod)
                continue
            remapped.append(
                FigureModification(
                    target_parameter="size_max",
                    old_value=current_max,
                    new_value=new_max,
                    reason=mod.reason or "Resize bubble scale_size_area max_size",
                    confidence=mod.confidence,
                )
            )
            current_max = float(new_max)
        return remapped

    def _parse_rules(
        self,
        text: str,
        payload: dict[str, Any],
        *,
        forbidden: set[str] | None = None,
    ) -> ModificationRequest:
        matched: list[FigureModification] = []
        used_rule_ids: set[str] = set()
        compact = text.lower()
        rules_by_id = {str(rule.get("id", "")): rule for rule in self.rules}
        forbidden = forbidden or set()

        # Prefer composite rules before atomic ones to avoid double application.
        ordered_rules = sorted(
            self.rules,
            key=lambda rule: 0 if str(rule.get("id")) == "outer_thick_inner_thin" else 1,
        )
        for rule in ordered_rules:
            keywords = rule.get("keywords", [])
            if not any(str(keyword).lower() in compact or str(keyword) in text for keyword in keywords):
                continue
            rule_id = str(rule.get("id", ""))
            if rule_id in used_rule_ids:
                continue
            if self._rule_forbidden(rule, forbidden):
                continue
            used_rule_ids.add(rule_id)
            if rule_id == "outer_thick_inner_thin":
                used_rule_ids.update({"thicken_axis_lines", "thin_threshold_lines", "thin_axis_lines", "thicken_threshold_lines"})
            matched.extend(self._operation_to_modifications(rule, payload, text))

        if not matched:
            for pattern, rule_id in LOCAL_PARAPHRASE_PATTERNS:
                if rule_id in used_rule_ids:
                    continue
                if not pattern.search(text):
                    continue
                rule = rules_by_id.get(rule_id)
                if not rule or self._rule_forbidden(rule, forbidden):
                    continue
                used_rule_ids.add(rule_id)
                if rule_id == "outer_thick_inner_thin":
                    used_rule_ids.update({"thicken_axis_lines", "thin_threshold_lines", "thin_axis_lines"})
                matched.extend(self._operation_to_modifications(rule, payload, text))

        # Special case: thicken wording + explicit not-full-border.
        if self._wants_thicker_axis(text) and "panel_border=full" in forbidden:
            if not any(m.target_parameter == "line_width" for m in matched):
                rule = rules_by_id.get("thicken_axis_lines")
                if rule:
                    matched.extend(self._operation_to_modifications(rule, payload, text))
            matched.extend(
                self._operation_to_modifications(
                    {"parameter": "panel_border", "operation": "set", "value": "none", "confidence": 0.95},
                    payload,
                    text,
                    reason="User rejected full panel.border",
                )
            )

        matched = self._filter_forbidden(matched, forbidden)
        if not matched:
            return ModificationRequest(
                unmatched=True,
                message="No design-parameter refinement matched the request",
            )
        return ModificationRequest(modifications=matched, message="ok")

    def _parse_llm(self, text: str, payload: dict[str, Any]) -> ModificationRequest:
        summary = {
            "journal_style": payload.get("journal_style")
            or (payload.get("style_profile") or {}).get("journal_style"),
            "width_mm": (payload.get("size") or {}).get("width_mm")
            or (payload.get("visual_parameters") or {}).get("width_mm"),
            "font_axis_text_size": (payload.get("font") or {}).get("axis_text_size")
            or (payload.get("visual_parameters") or {}).get("font_size"),
            "point_size": (payload.get("geometry") or {}).get("point_size")
            or (payload.get("visual_parameters") or {}).get("point_size"),
            "line_width": (payload.get("geometry") or {}).get("line_width")
            or (payload.get("visual_parameters") or {}).get("line_width"),
            "threshold_line_width": (payload.get("geometry") or {}).get("threshold_line_width")
            or (payload.get("visual_parameters") or {}).get("threshold_line_width"),
            "border": (payload.get("theme") or {}).get("border")
            or (payload.get("visual_parameters") or {}).get("border"),
            "legend_position": (payload.get("theme") or {}).get("legend_position")
            or (payload.get("visual_parameters") or {}).get("legend_position"),
            "grid": (payload.get("theme") or {}).get("grid")
            or (payload.get("visual_parameters") or {}).get("grid"),
        }
        content = self.llm_client.complete(
            [
                {"role": "system", "content": REFINEMENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": refinement_user_message(
                        text,
                        summary,
                        learned_examples=self.learner.prompt_examples(),
                    ),
                },
            ]
        )
        data = extract_json_object(content)
        blob = json.dumps(data, ensure_ascii=False).lower()
        forbidden_tokens = ("ggsave", "library(", "complexheatmap", "log2fc_threshold", "fdr_threshold")
        if any(token in blob for token in forbidden_tokens):
            raise ValueError("LLM attempted forbidden refinement content")

        if not data.get("matched", True):
            return ModificationRequest(
                unmatched=True,
                message=str(data.get("reason") or "LLM reported no design match"),
            )

        operations = data.get("operations") or []
        if not isinstance(operations, list) or not operations:
            return ModificationRequest(unmatched=True, message="LLM returned empty operations")

        matched = self._ops_dicts_to_modifications(operations, payload, text)
        if not matched:
            return ModificationRequest(unmatched=True, message="LLM operations produced no patches")
        return ModificationRequest(modifications=matched, message="ok")

    def _ops_dicts_to_modifications(
        self,
        operations: list[dict[str, Any]],
        payload: dict[str, Any],
        text: str,
    ) -> list[FigureModification]:
        matched: list[FigureModification] = []
        for item in operations:
            if not isinstance(item, dict):
                continue
            parameter = str(item.get("parameter", "")).strip()
            operation = str(item.get("operation", "set")).strip().lower()
            if parameter not in ALLOWED_PARAMETERS and parameter not in PARAMETER_PATHS:
                # Allow dotted paths already in PARAMETER_PATHS values via set.
                if "." not in parameter:
                    raise ValueError(f"LLM parameter not allowed: {parameter}")
            if operation not in ALLOWED_OPERATIONS:
                raise ValueError(f"LLM operation not allowed: {operation}")
            rule_like = {
                "parameter": parameter,
                "operation": operation,
                "value": item.get("value"),
                "confidence": float(item.get("confidence", 0.8)),
            }
            if rule_like["value"] is None and operation == "increase" and parameter == "font_size":
                rule_like["value"] = 2
            if rule_like["value"] is None and operation == "decrease" and parameter == "font_size":
                rule_like["value"] = 1
            if rule_like["value"] is None and operation == "decrease" and parameter == "point_size":
                rule_like["value"] = 0.5
            if rule_like["value"] is None and operation == "increase" and parameter == "point_size":
                rule_like["value"] = 0.5
            if rule_like["value"] is None and operation == "increase" and parameter == "line_width":
                rule_like["value"] = 0.3
            if rule_like["value"] is None and operation == "decrease" and parameter == "line_width":
                rule_like["value"] = 0.2
            if rule_like["value"] is None and operation == "increase" and parameter == "threshold_line_width":
                rule_like["value"] = 0.15
            if rule_like["value"] is None and operation == "decrease" and parameter == "threshold_line_width":
                rule_like["value"] = 0.15
            if parameter == "outer_thick_inner_thin":
                matched.extend(
                    self._operation_to_modifications(
                        {
                            "parameter": "outer_thick_inner_thin",
                            "operation": "preset",
                            "value": {},
                            "confidence": float(item.get("confidence", 0.9)),
                        },
                        payload,
                        text,
                        reason=str(item.get("reason") or f"User requested: {text}"),
                    )
                )
                continue
            if parameter == "nature_single_column" and operation == "preset" and not isinstance(rule_like["value"], dict):
                rule_like["value"] = {
                    "journal_style": "Nature",
                    "size.column": "single",
                    "size.width_mm": 89,
                }
            matched.extend(
                self._operation_to_modifications(
                    rule_like,
                    payload,
                    text,
                    reason=str(item.get("reason") or f"User requested: {text}"),
                )
            )
        return matched

    def _operation_to_modifications(
        self,
        rule: dict[str, Any],
        payload: dict[str, Any],
        user_text: str,
        *,
        reason: str | None = None,
    ) -> list[FigureModification]:
        parameter = str(rule["parameter"])
        operation = str(rule.get("operation", "set"))
        value = rule.get("value")
        confidence = float(rule.get("confidence", 0.8))
        reason_text = reason or f"User requested: {user_text}"

        if operation == "preset" and isinstance(value, dict):
            if parameter == "outer_thick_inner_thin":
                return self._operation_to_modifications(
                    {"parameter": "line_width", "operation": "increase", "value": 0.3, "confidence": confidence},
                    payload,
                    user_text,
                    reason=reason_text,
                ) + self._operation_to_modifications(
                    {
                        "parameter": "threshold_line_width",
                        "operation": "decrease",
                        "value": 0.15,
                        "confidence": confidence,
                    },
                    payload,
                    user_text,
                    reason=reason_text,
                )
            return [
                FigureModification(
                    target_parameter=parameter,
                    old_value=None,
                    new_value=value,
                    reason=reason_text,
                    confidence=confidence,
                )
            ]

        if operation == "palette":
            return [
                FigureModification(
                    target_parameter="colors",
                    old_value=None,
                    new_value=str(value),
                    reason=reason_text,
                    confidence=confidence,
                )
            ]

        paths = self.mapper.paths_for(parameter, payload)
        if not paths and operation == "set":
            return [
                FigureModification(
                    target_parameter=parameter,
                    old_value=None,
                    new_value=value,
                    reason=reason_text,
                    confidence=confidence,
                )
            ]
        if not paths:
            raise ValueError(f"Unknown refinement parameter: {parameter}")

        ref_path = paths[0]
        current = self.mapper.read_path(payload, ref_path)
        if current is None and operation in {"increase", "decrease", "multiply"}:
            current = 0
        new_value = self.mapper.compute_new_value(current, operation, value)
        return [
            FigureModification(
                target_parameter=parameter if parameter in PARAMETER_PATHS else ref_path,
                old_value=current,
                new_value=new_value,
                reason=reason_text,
                confidence=confidence,
            )
        ]

    @staticmethod
    def _negation_forbidden(text: str) -> set[str]:
        forbidden: set[str] = set()
        if re.search(r"(不是|不要|别|别改成|而不是).{0,8}(全边框|四周|方框|panel\s*border|boxed)", text, re.I):
            forbidden.add("panel_border=full")
        if re.search(r"(不是|不要|别).{0,6}(网格|grid)", text, re.I):
            forbidden.add("theme.grid=major")
        return forbidden

    @staticmethod
    def _wants_thicker_axis(text: str) -> bool:
        return bool(re.search(r"加粗|轴线|线粗|边框加粗|加粗边框", text))

    @staticmethod
    def _rule_forbidden(rule: dict[str, Any], forbidden: set[str]) -> bool:
        parameter = str(rule.get("parameter", ""))
        value = rule.get("value")
        token = f"{parameter}={value}"
        return token in forbidden

    @staticmethod
    def _filter_forbidden(
        mods: list[FigureModification],
        forbidden: set[str],
    ) -> list[FigureModification]:
        if not forbidden:
            return mods
        kept: list[FigureModification] = []
        for mod in mods:
            token = f"{mod.target_parameter}={mod.new_value}"
            # Also catch panel_border logical name mapped later.
            if token in forbidden:
                continue
            if "panel_border=full" in forbidden and mod.target_parameter in {"panel_border", "theme.border"}:
                if str(mod.new_value) in {"full", "panel"}:
                    continue
            kept.append(mod)
        return kept

    @staticmethod
    def _logical_name(mod: FigureModification) -> str:
        path = mod.target_parameter
        if path.startswith("geometry.line_width") or path.startswith("visual_parameters.line_width"):
            return "line_width"
        if path.startswith("geometry.threshold_line_width") or path.startswith(
            "visual_parameters.threshold_line_width"
        ):
            return "threshold_line_width"
        if path.startswith("theme.border") or path.startswith("visual_parameters.border"):
            return "panel_border"
        if path.startswith("theme.grid") or path.startswith("visual_parameters.grid"):
            return "theme.grid"
        if path.startswith("visual_parameters.font_size") or path.startswith("font."):
            return "font_size"
        return path

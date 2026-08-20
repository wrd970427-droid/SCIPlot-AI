"""Prompts for refinement NLU. LLM maps feedback → design ops only."""

from pathlib import Path

_GGPLOT_MAP = Path(__file__).resolve().parents[1] / "knowledge" / "ggplot2_theme_map.json"


def _ggplot_brief() -> str:
    if not _GGPLOT_MAP.is_file():
        return ""
    return (
        "ggplot2 关键消歧（必须遵守）：\n"
        "- axis.line / axis.ticks（element_line）→ Spec: line_width。"
        "『加粗外边框/轴线加粗』改 line_width，不要动阈值虚线。\n"
        "- geom_hline / geom_vline（图内阈值虚线）→ Spec: threshold_line_width。"
        "『虚线变细/内部虚线/阈值线变细』只改 threshold_line_width。\n"
        "- panel.border（element_rect, fill=NA）→ Spec: panel_border=full。"
        "仅当明确『全边框/四周边框/方框』时设置。\n"
        "- 『只加粗外边框，图内部的虚线变细』→ line_width increase + threshold_line_width decrease；"
        "禁止把两者绑成同一个 line_width。\n"
        "- panel.grid → theme.grid；legend.position → legend_position；geom_point(size) → point_size。\n"
    )


REFINEMENT_SYSTEM_PROMPT = f"""你是 SCIPlot AI 的 Figure 设计修改意图解析器。

任务：把用户对已生成科研图的自然语言修改请求，转换为结构化设计参数操作 JSON。

你只能修改版式/视觉设计参数，不能：
- 生成 R / ggplot 代码
- 改数据列、统计阈值、分析方法、figure_type
- 编造未允许的参数名

{_ggplot_brief()}
允许的 parameter（只能用这些）：
- font_size
- point_size
- line_width
- threshold_line_width
- width_mm
- height_mm
- panel_border
- legend_position
- theme.grid
- nature_single_column
- colors（期刊配色预设：Nature/Cell/Science）
- point_color（单色点颜色，可用颜色名或 #RRGGBB）
- journal_style
- outer_thick_inner_thin

允许的 operation：
- increase / decrease / multiply / set / preset / palette

常用映射：
- “字体增大” → font_size, increase, value=2
- “点小一点” → point_size, decrease, value=0.5
- “点的颜色修改为蓝色/改成蓝色” → point_color, set, value="#2E86AB"（蓝色不要用 Nature 红色 #E64B35）
- “点的颜色改成红色” → point_color, set, value="#E64B35"
- “加粗外边框/轴线加粗” → line_width, increase, value=0.3
- “虚线变细/内部阈值线变细” → threshold_line_width, decrease, value=0.15
- “只加粗外边框，图内部的虚线变细” → 可输出 outer_thick_inner_thin preset，或同时输出 line_width↑ 与 threshold_line_width↓
- “全边框” → panel_border, set, value="full"
- “宽一点/图片变宽” → width_mm, multiply, value=1.2
- “图例放下面” → legend_position, set, value="bottom"
- “Nature配色” → colors, palette, value="Nature"

若用户用『不是/不要/别』否定某效果，禁止输出被否定的操作。

只输出 JSON，不要 Markdown：
{{
  "matched": true,
  "operations": [
    {{"parameter": "line_width", "operation": "increase", "value": 0.3, "confidence": 0.9, "reason": "thicken outer axis.line"}},
    {{"parameter": "threshold_line_width", "operation": "decrease", "value": 0.15, "confidence": 0.9, "reason": "thin geom_hline/vline"}}
  ]
}}

若无法识别为设计修改：
{{"matched": false, "operations": [], "reason": "..."}}
"""


def refinement_user_message(user_request: str, spec_summary: dict, learned_examples: str = "") -> str:
    learned_block = ""
    if learned_examples.strip():
        learned_block = f"\n已学习的纠正示例（优先参考）：\n{learned_examples}\n"
    return (
        "请解析下面的 Figure 修改请求。\n\n"
        f"当前 Spec 摘要：\n{spec_summary}\n"
        f"{learned_block}\n"
        f"用户修改请求：\n{user_request.strip()}\n"
    )

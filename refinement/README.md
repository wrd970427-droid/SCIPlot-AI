# Figure Refinement Agent

用户对已生成 Figure 做自然语言设计修改，例如「字体大一点」「点小一点」。

所有 Figure 共用同一条 Refine 路径，不按图类型拆 Agent。

```
User Feedback
→ RefinementAgent（logical params: font_size / point_size / …）
→ ParameterMapper（按 Spec 形状解析物理路径）
→ SpecHistory
→ Codegen（volcano agent 或 Generic Strategy）
→ QC
```

- 火山图 Spec：`font.axis_text_size` / `geometry.point_size` / …
- Generic Spec：`visual_parameters.font_size` / `visual_parameters.point_size` / …

禁止：新 Figure 类型、统计阈值、数据列、重新分析。

ggplot2 关键消歧见 `knowledge/ggplot2_theme_map.json`：
- 加粗边框 / 轴线 → `geometry.line_width`（axis.line）
- 全边框 / 四周框 → `theme.border=full`（panel.border）

学习库：`knowledge/learned_refinements.json`（仅设计操作，不含数据）。


## 文件

```
refinement/
├── README.md
├── __init__.py
├── refinement_agent.py
└── parameter_mapper.py

knowledge/refinement_rules.json
schemas/figure_modification.py
schemas/spec_history.py
```

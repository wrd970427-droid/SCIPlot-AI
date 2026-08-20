# SCIPlot AI Knowledge Base

本目录把 SCI 绘图经验写成**可被 Agent 读取的 JSON**，不是运行时代码。

后续 Requirement / Specification / Revision / QC Agent 只查询这里的规则，再写入 `FigureSpecification`。本阶段没有 Python 加载器，也没有 Agent。

## 作用

| 能力 | 知识来源 |
|------|----------|
| 期刊默认宽高、字体、dpi | `journals/journal_styles.json` |
| 火山图要问什么、默认阈值、统计/视觉规则 | `figure_rules/volcano.json` |
| 「字体大一点」如何改 Spec / ggplot | `ggplot_mapping/ggplot_mapping.json` |

原则：

1. 能对应到 `schemas/figure_spec.py` 的字段，就写 `spec_path`。
2. 期刊数字区分 `official_requirement` 与 `recommended_default`。没有官方条文的，一律标后者，禁止写成硬性期刊要求。
3. 默认高度、配色、ggplot theme 几乎都是 recommended_default。

## 目录

```
knowledge/
├── README.md
├── journals/
│   └── journal_styles.json
├── figure_rules/
│   └── volcano.json
└── ggplot_mapping/
    └── ggplot_mapping.json
```

V0.1 只提供 volcano 规则。以后增加 heatmap / KM 时，在 `figure_rules/` 新增 `{type}.json`，期刊文件不必复制。

## 各文件用途

### `journals/journal_styles.json`

第一批：Nature、Cell、Science、Nature Communications、Cancer Cell、Microbiome、mSystems。

每个期刊包含：

- `single_column` / `double_column`（以及期刊若有的 1.5 栏、三栏）
- `font`、`line`、`output`、`margin`、`theme`
- 每项的 `status`
- `sources`（官方指南 URL）
- `spec_defaults`：可直接 merge 进 `FigureSpecification` 的公共层

**不要**假设所有期刊都是 89 / 183 mm。Science 单栏是 **57 mm**，Cell / Cancer Cell 是 **85 / 174 mm**，Microbiome（BMC）是 **85 / 170 mm**。

Cancer Cell 没有独立插图尺寸表，显式 `inherits: Cell`，数值来自 Cell Press 统一指南。

### `figure_rules/volcano.json`

描述火山图：

- `required_parameters`：data_file、gene_column、log2FC_column、pvalue_column
- `optional_parameters`：label、配色、点大小、alpha、阈值线、注释
- `default_parameters`：|log2FC|≥1，FDR≤0.05，point_size 1.5
- `user_questions`：按 `round` 分组，供 Requirement Agent **每轮最多 3 问**
- `statistical_rules` / `visual_rules`

`pvalue_column` 是显著性数值列（可能是 `pvalue` 或 `padj`）。真正用 p 还是 FDR，由问题「你的显著性指标是什么？」写入 `significance_metric`。

### `ggplot_mapping/ggplot_mapping.json`

把自然语言修订编成 intent：

| 类别 | 例子 | 结果 |
|------|------|------|
| size | 点小一点 | `geometry.point_size = 1` |
| size | 字体大一点 | `axis_text_size / axis_title_size / legend_size +2` |
| size | 线条细一点 | `geometry.line_width = 0.4`（下限 0.3） |
| theme | 白色背景 / 不要网格 | `theme_classic()`，`grid=none` |
| border | 加边框 | `panel.border = element_rect` |
| color | Nature风格 | `nature_palette`（**非** Nature 官方配色） |
| layout | 适合论文单栏 | `apply_journal_column: single`（读当前期刊 width，不写死 89） |

## 未来 Agent 如何调用（尚未实现）

以下是约定，不是本阶段代码。

**1. 期刊默认值 → Spec 公共层**

```text
journal = user.journal_style or "Nature"
profile = journal_styles.journals[journal]
spec.public_fields = profile.spec_defaults
```

**2. 火山图追问**

```text
rules = figure_rules/volcano.json
missing = required_parameters whose spec_path is empty
questions = user_questions
              where required and not skip_if_known
              sort by round
              take max_questions_per_turn (3)
```

用户说「帮我画一个 Nature 风格 RNA-seq 火山图」时：`figure_type`、`journal_style` 已知，round 1 只补用途和尺寸；不要再问「目标期刊是什么」。

**3. 自然语言改图**

```text
for intent in ggplot_mapping.intents:
    if user_text matches intent.utterances:
        apply intent.patches to FigureSpecification
        if op == apply_journal_column:
            width = journals[spec.journal_style][column].width_mm
```

**4. QC**

对照 `journal_styles` 的官方下限（字号、线宽、栏宽）和 `figure_rules/volcano.json` 的 visual_rules（图例占比、阈值线）。recommended_default 只能警告，不能当成投稿硬失败，除非同时落在 Schema 的 publication 约束里（字号 ≥6 pt，线宽 ≥0.3）。

## 与 Figure Specification 的关系

知识库是**推荐与提问**；`schemas/figure_spec.py` 是**校验后的唯一真相源**。

冲突时：用户显式值 > 期刊 `spec_defaults` > volcano `default_parameters`。

V0.1 Schema 的 `JournalStyle` 枚举目前只有 Nature / Cell / Science / Custom。知识库已含 Nature Communications、Cancer Cell、Microbiome、mSystems；接入 Spec Agent 时需要扩展枚举，或暂映射到 Custom 并保留期刊名于 notes。

## 本阶段明确没有

- 任何 Agent / API / 前端
- 知识库 Python loader
- R 代码或 Docker
- heatmap 等其他 figure_rules

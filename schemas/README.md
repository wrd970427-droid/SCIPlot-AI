# Figure Specification Schema（V0.1）

本模块定义 SCIPlot AI 的**唯一参数协议**。后续 Requirement Agent、R Code Agent、QC Agent 都只读写 `FigureSpecification`，禁止在绘图代码里硬编码字号、线宽、阈值或尺寸。

V0.1 只实现 **volcano**。`FigureType` 已预留 heatmap / survival / UMAP 等枚举值，但校验器会拒绝非 volcano 类型。

## 文件

```
schemas/
├── README.md
├── __init__.py
├── figure_spec.py
├── qc_report.py
└── examples/
    └── volcano_nature_rnaseq.json
```

## 分层

| 层 | 模型 | 作用 |
|----|------|------|
| 公共层 | `SizeSpec` `FontSpec` `ThemeSpec` `GeometrySpec` `OutputSpec` | 所有 Figure 共用 |
| 类型层 | `VolcanoPlotSpec`（字段 `plot`） | 火山图数据列、统计阈值、标签、配色 |

以后新增 heatmap 时：新增 `HeatmapPlotSpec`，将 `plot` 改为带 `figure_type` discriminator 的 Union。公共层不必改。

## 默认值（Nature 单栏投稿）

- `purpose=publication`，`journal_style=Nature`
- `width_mm=89`，`height_mm=70`，`dpi=600`
- 字体 Arial：axis 7 / title 8 / legend 7
- `theme`：白底、无网格、无边框
- `point_size=1.5`，`line_width=0.5`，`alpha=0.7`
- `|log2FC| >= 1`，`FDR <= 0.05`

投稿约束（`purpose=publication`）：

- 字号 ≥ 6 pt
- `line_width` ≥ 0.3

`purpose=internal` 时不强制上述下限。

## 阻塞字段

以下字段允许为 `null`（Requirement Agent 尚未问到），但 `is_complete_for_codegen()` 为 False 时**不得**进入 R 代码生成：

- `plot.data.log2fc_column`
- `plot.data.significance_column`
- `plot.data.gene_column`

## 解析示例

```python
from schemas import load_figure_specification, FigureSpecification

spec = load_figure_specification(Path("schemas/examples/volcano_nature_rnaseq.json").read_text())
assert spec.figure_type.value == "volcano"
assert spec.size.width_mm == 89
assert spec.is_complete_for_codegen()
```

## 测试

见仓库 `tests/test_figure_spec.py`。在项目根目录：

```bash
pip install -r requirements.txt
python -m pytest tests/test_figure_spec.py -v
```

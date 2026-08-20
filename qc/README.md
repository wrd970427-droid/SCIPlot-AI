# Figure QC Agent（V0.1）

独立出版规范检查器。不改 Spec、不改图、不生成 R、不执行 R、不调用 LLM。

## 文件

```
qc/
├── README.md
├── __init__.py
├── figure_qc_agent.py
└── rules.py
```

阈值全部在 `rules.py`（字号、线宽、点大小、dpi、栏宽偏差）。

## 输入 / 输出

```python
from qc import FigureQCAgent
from schemas import load_figure_specification

spec = load_figure_specification(Path("schemas/examples/volcano_nature_rnaseq.json").read_text())
report = FigureQCAgent().check(spec, "output")
# output/QC_report.json
```

`status`：`pass` / `warning` / `failed`

检查项：文件（pdf/svg/png）、尺寸 vs 期刊栏宽、dpi、字号、point_size / line_width / alpha。

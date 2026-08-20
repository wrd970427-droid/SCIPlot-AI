# Agents（V0.1）

本目录只包含当前已实现的 Agent。不调用 LLM，不执行 R，不启动 Docker。

## 文件

```
agents/
├── README.md
├── __init__.py
├── knowledge_loader.py
├── volcano_requirement_agent.py
└── volcano_r_code_agent.py
```

## Volcano Requirement Agent

需求识别、缺参追问、生成 `FigureSpecification`。见 `volcano_requirement_agent.py`。

## Volcano R Code Agent

输入只能是 `FigureSpecification`。把 Spec 编译成 `volcano.R`（ggplot2 + ggrepel + svglite）。

不读取自然语言，不重新从文本判断 figure 类型，不写死字号/阈值/点大小。

```python
from agents import VolcanoRCodeAgent
from schemas import load_figure_specification

spec = load_figure_specification(Path("schemas/examples/volcano_nature_rnaseq.json").read_text())
code = VolcanoRCodeAgent().generate(spec, output_path="volcano.R")
```

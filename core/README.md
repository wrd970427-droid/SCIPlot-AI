# Generic Figure Engine

从「一个 Figure 一个 Agent」升级为 Catalog 驱动的通用执行框架。

## 流程

```
User Request
→ Figure Registry (catalog metadata)
→ Requirement Engine (FigureDefinition.required_fields)
→ Specification Builder → GenericFigureSpecification
→ Code Generation Engine (strategy)
→ Execution Manager → R
→ QC Manager
```

## 扩展新 Figure

1. `knowledge/scientific_figures` catalog entry  
2. data schema（如需）  
3. `core/strategies/<name>_strategy.py` 并注册到 `CodeGenerationEngine`  
4. 将 `implementation_status` 提升到可执行级别  

不需要新建 Requirement Agent / Workflow。

## 已实现（Generic Engine）

1. `transcriptomics.volcano` — `VolcanoStrategy` + adapter  
2. `basic_statistics.boxplot` — `BoxplotStrategy`（variants: boxplot / violin）

## Volcano

现有 `agents/volcano_*` 保留；通过 `core/adapters/volcano_adapter.py` + `VolcanoStrategy` 接入。

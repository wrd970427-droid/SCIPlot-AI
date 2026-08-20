# Scientific Figure Catalog / Ontology

SCIPlot AI 的科研绘图知识底座（taxonomy + metadata）。

**本目录不是实现层**：不包含第三方 R 源码复制，不假装未实现的图已可运行。

## 文件

| 文件 | 作用 |
|---|---|
| `catalog.json` | 全部 Figure families |
| `taxonomy.json` | 一级分类与细分 |
| `data_schemas.json` | 数据结构角色库 |
| `package_registry.json` | R package 注册表（仅登记，不改 Docker） |
| `composition_rules.json` | 多图组合建议 |
| `source_registry.json` | FigureYa 等外部映射（仅 metadata） |
| `<category>/*.json` | 按分类拆分的 FigureDefinition |

## 原则

- `statistical_parameters` 与 `visual_parameters` 严格分离（Refinement 边界）
- Hospital Private：`privacy.local_only` 必须包含原始行列/患者级数值
- `implementation_status` 诚实标注；当前仅 `transcriptomics.volcano` 为已实现闭环

重新生成：

```bash
python knowledge/scientific_figures/_generate_catalog.py
```

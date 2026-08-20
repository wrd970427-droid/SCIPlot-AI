# SCIPlot Figure Catalog Report

Generated for the Scientific Figure Catalog / Ontology phase.

## 1. New directory structure

```
knowledge/scientific_figures/
├── README.md
├── loader.py
├── _generate_catalog.py
├── catalog.json
├── taxonomy.json
├── package_registry.json
├── data_schemas.json
├── composition_rules.json
├── source_registry.json
├── basic_statistics/
├── transcriptomics/
├── enrichment/
├── clinical/
├── machine_learning/
├── single_cell/
├── spatial_omics/
├── mutation_genomics/
├── genomics/
├── comparative_genomics/
├── microbiome/
├── network/
├── cell_communication/
├── multiomics/
└── time_series/

schemas/figure_definition.py
tests/test_figure_catalog.py
SCIPLOT_FIGURE_CATALOG_REPORT.md
```

Hospital Private Privacy Gateway：**当前分支未落地独立 Gateway 代码**（此前仅讨论架构）。Catalog 内每条 Figure 已预置 `privacy.llm_allowed` / `privacy.local_only` 字段，供后续 Gateway 使用。

## 2. Scientific Figure Taxonomy（一级分类）

| Category | Meaning |
|---|---|
| basic_statistics | 基础分布与比较图 |
| transcriptomics | 转录组 / 差异丰度 |
| enrichment | 功能富集 ORA/GSEA |
| clinical | 生存 / 诊断 / 预后 |
| machine_learning | 模型诊断视图 |
| single_cell | 单细胞 |
| spatial_omics | 空间组学 |
| mutation_genomics | 突变 / CNV |
| genomics | 基因组轨道 / 关联 |
| comparative_genomics | 比较基因组 / 进化 |
| microbiome | 微生物组 |
| network | 网络与流量图 |
| cell_communication | 细胞通讯 |
| multiomics | 多组学整合视图 |
| time_series | 时间序列 |

## 3. Figure families 总数

**86**（目标 ≥50，已超额）

## 4. 每个一级 category 数量

| Category | Count |
|---|---:|
| basic_statistics | 10 |
| clinical | 10 |
| single_cell | 10 |
| transcriptomics | 9 |
| mutation_genomics | 8 |
| enrichment | 7 |
| comparative_genomics | 7 |
| machine_learning | 5 |
| network | 5 |
| microbiome | 4 |
| genomics | 3 |
| spatial_omics | 2 |
| cell_communication | 2 |
| multiomics | 2 |
| time_series | 2 |
| **Total** | **86** |

## 5. FigureYa 映射统计

来源：`https://github.com/ying-ge/FigureYa` + `all_included.txt`（公开列表）

| Metric | Value |
|---|---:|
| all_included.txt 模块数 | **199** |
| 本阶段完成映射的模块数 | **43** |
| 归并得到的 Figure families 数 | **36** |
| 未机械复制 Rmd/源码 | 是（仅 metadata mapping） |

说明：目标不是 1:1 复制 199 个模块，而是归并为 SCIPlot Figure families + variants + use cases。

## 6. R package registry 统计

**36** packages registered（CRAN / Bioconductor / GitHub）

Core-required（现有 volcano 闭环相关）：`ggplot2`, `ggrepel`, `patchwork`（registry 标记；Docker 未在本阶段扩展）

## 7. Data Schema 数量

**54** abstract data schemas in `data_schemas.json`

## 8. Composition Rule 数量

**8** multi-panel composition rules

## 9. capability_level 数量

| Level | Count |
|---|---:|
| core | 37 |
| advanced | 42 |
| experimental | 7 |

## 10. Catalog validation 测试结果

```
python -m pytest tests/test_figure_catalog.py -v
→ 10 passed
```

覆盖：唯一 id、taxonomy、data schema、package registry、统计/视觉参数不重叠、implementation_status、privacy、sources、volcano 映射、composition/source registry。

## 11. 当前真正已经实现的 Figure 数量

### IMPLEMENTED（可跑通 SCIPlot 闭环）

| id | implementation_status | 说明 |
|---|---|---|
| `transcriptomics.volcano` | `qc_verified` | Spec → Requirement → R → Execution → QC → Refinement |

**IMPLEMENTED count = 1**

### CATALOGUED（仅知识条目）

其余 **85** 个 Figure families：`implementation_status = catalog_only`

**禁止将 CATALOGUED 视为已支持绘图。**

## 12. 下一阶段最值得实现的 Top 10 Figure families

按临床/生信高频、与现有 ggplot2 栈接近、可复用 Spec/QC 模式排序：

1. `transcriptomics.PCA`
2. `transcriptomics.DEG_heatmap`（ComplexHeatmap，advanced）
3. `basic_statistics.boxplot`
4. `basic_statistics.violin`
5. `enrichment.ORA_dotplot`
6. `enrichment.GSEA_running_score`
7. `clinical.Kaplan_Meier`
8. `clinical.ROC`
9. `single_cell.UMAP`
10. `mutation_genomics.oncoplot`

## Explicit distinction

| Bucket | Meaning | Count |
|---|---|---:|
| **CATALOGUED** | Ontology / metadata only | 86 |
| **IMPLEMENTED** | End-to-end runnable in SCIPlot today | 1 |

本阶段未实现任何新 Figure Agent，未修改 Volcano Workflow / Docker packages / 未批量复制 FigureYa 源码。

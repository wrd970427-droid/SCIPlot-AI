# Generic Figure Engine Architecture

## 1. 为什么从 Figure-specific Agent 升级

V0.1 以 `VolcanoRequirementAgent` + `VolcanoRCodeAgent` + `FigureWorkflow` 打通闭环，但每个新 Figure 若复制一套 Agent/Workflow，成本线性爆炸，且与 86 个 Catalog families 的知识底座脱节。

Generic Figure Engine 把「科学元数据 / 缺参追问 / Spec 构建 / 代码生成 / 执行 / QC」拆成可复用层，**Catalog 成为唯一真相源**。

## 2. Figure Catalog 如何驱动系统

```
catalog.json (FigureDefinition)
        │
        ├─ required_fields     → RequirementEngine 自动生成 missing / questions
        ├─ statistical_parameters / visual_parameters → Spec defaults
        ├─ data_schema_id      → 数据结构约束
        ├─ implementation_status → 是否允许执行
        └─ retrieval_keywords  → FigureRegistry.search_figures
```

`catalog_only` → 明确拒绝：`Figure cataloged but implementation unavailable`  
`qc_verified` / `execution_verified` / `code_generation_ready` → 可进入代码生成与执行（需已注册 Strategy）

## 3. Generic Workflow

```
User Request + figure_id
        ↓
FigureRegistry.get_figure_definition
        ↓
implementation_status gate
        ↓
RequirementEngine.collect (definition-driven)
        ↓
SpecificationBuilder → GenericFigureSpecification
        ↓
CodeGenerationEngine.generate (strategy pattern)
        ↓
ExecutionManager.execute_figure
        ↓
QCManager.run_qc
```

核心目录：

```
core/
├── figure_engine.py
├── figure_registry.py
├── requirement_engine.py
├── specification_builder.py
├── code_generation_engine.py
├── execution_manager.py
├── qc_manager.py
├── adapters/volcano_adapter.py
└── strategies/
    ├── volcano_strategy.py
    └── boxplot_strategy.py
```

## 4. Volcano 迁移过程

- **不删除** `agents/volcano_requirement_agent.py`、`agents/volcano_r_code_agent.py`
- **不改动**现有 Web Demo Workflow（仍走原路径，保证回归）
- 新增 `VolcanoAdapter`：`GenericFigureSpecification` → 旧 `FigureSpecification`
- 新增 `VolcanoStrategy`：注册到 `CodeGenerationEngine`
- 旧火山 Spec/QC/R 生成逻辑复用，作为 reference implementation

## 5. Second Figure Validation（`basic_statistics.boxplot`）

Generic Engine 已成功支持第二个 Figure family，**未**新增 BoxplotRequirementAgent / BoxplotWorkflow / 独立 API。

| 组件 | 变更 |
|---|---|
| Catalog | `implementation_status` → `execution_verified`；`variants`: boxplot / violin |
| Data schema | 新增 `group_numeric_table`（required: group, value） |
| Strategy | `core/strategies/boxplot_strategy.py` → 注册到 `CodeGenerationEngine` |
| QC | `QCManager` 对非 volcano 使用共享文件存在性 QC |

**IMPLEMENTED：**

1. `transcriptomics.volcano`
2. `basic_statistics.boxplot`
3. `basic_statistics.scatter`（Web Demo 已接入：LLM 只解析图类型与列映射，R 仍由 Strategy 生成）

证明：新增 Figure 只需 **FigureDefinition + DataSchema + Strategy**，不需要独立 Agent / Workflow。

演示：`python examples/demo_boxplot_generic_engine.py [--no-execute]`

## 6. 未来扩展 Heatmap / KM / UMAP

对每个新图：

1. Catalog 条目已存在（或补全）→ 将 `implementation_status` 提升  
2. 如需新数据结构 → `data_schemas.json`  
3. 新增 `core/strategies/<figure>_strategy.py` 并 `register()`  
4. （可选）QC 规则扩展到 `QCManager`  
5. **不需要**新 Requirement Agent / 新 Workflow

统计参数与视觉参数继续由 Catalog 分隔，供 Refinement 使用。

## 7. Refine：版式 Spec + LLM R 代码编辑

Generate 仍由 Strategy 产出底稿 R（可重复、可测）。Refine 采用双后端：

1. **版式 Refine**：`RefinementAgent` 改 `font_size` / `point_color` / `size_max` 等 → 再从 Spec 生成 R  
2. **科学修改**：unmatched 或命中 `-log10` / 坐标轴变换等启发式 → `llm/r_code_editor.py` 直接改现有 R（只传指令、列名、Spec 摘要、当前脚本；**原始表数据不进 LLM**）→ 执行 → QC  

`SpecHistory` / `SpecVersion` 可选保存 `r_code`；Undo/Redo 恢复 Spec **与** R 快照后重跑，保证 Version 与图一致。

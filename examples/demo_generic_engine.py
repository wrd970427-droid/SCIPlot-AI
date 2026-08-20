"""演示 Generic Figure Engine（不经过 Web Demo）。

用法（在项目根目录）:

  python examples/demo_generic_engine.py
  python examples/demo_generic_engine.py --no-execute   # 只生成 Spec + R，不跑 R

演示内容:
  1. Catalog 规模与可执行 Figure
  2. unknown figure_id
  3. catalog_only（如 heatmap）被拒绝
  4. RequirementEngine 按 Definition 追问缺列
  5. transcriptomics.volcano 走完整 Generic 路径
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.figure_engine import FigureEngine
from core.figure_registry import FigureRegistry
from core.requirement_engine import RequirementEngine

EXAMPLE_CSV = ROOT / "examples" / "example_volcano.csv"
OUT_DIR = ROOT / "examples" / "demo_generic_output"


def _banner(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def demo_catalog(registry: FigureRegistry) -> None:
    _banner("1. Figure Catalog（仅 metadata）")
    all_figs = registry.list_available_figures()
    executable = [m for m in all_figs if m.is_executable]
    print(f"Catalogued families : {len(all_figs)}")
    print(f"Executable now      : {len(executable)}")
    for meta in executable:
        print(f"  - {meta.id}  [{meta.implementation_status.value}]")
    print("检索示例 search('volcano'):")
    for hit in registry.search_figures("volcano")[:3]:
        print(f"  - {hit.id} ({hit.implementation_status.value})")


def demo_unknown(engine: FigureEngine) -> None:
    _banner("2. Unknown figure_id")
    result = engine.run("does_not.exist")
    print(f"status  : {result.status}")
    print(f"message : {result.message}")


def demo_catalog_only(engine: FigureEngine) -> None:
    _banner("3. catalog_only → 拒绝执行（不假装支持）")
    result = engine.run("transcriptomics.DEG_heatmap")
    print(f"status  : {result.status}")
    print(f"message : {result.message}")


def demo_requirements(registry: FigureRegistry) -> None:
    _banner("4. RequirementEngine（由 FigureDefinition.required_fields 驱动）")
    definition = registry.get_figure_definition("transcriptomics.volcano")
    roles = [f.role for f in definition.required_fields]
    print(f"figure : {definition.id}")
    print(f"required_fields : {roles}")

    incomplete = RequirementEngine().collect(definition, answers={}, available_columns=[])
    print(f"\n空 answers → status={incomplete.status.value}")
    print(f"missing_fields : {incomplete.missing_fields}")
    for q in incomplete.questions:
        print(f"  ? {q}")

    ready = RequirementEngine().collect(
        definition,
        answers={
            "feature_id": "gene",
            "effect_size": "log2FoldChange",
            "significance": "padj",
        },
        available_columns=["gene", "log2FoldChange", "padj", "pvalue"],
    )
    print(f"\n补齐列映射 → status={ready.status.value}")
    print(f"known_mapping : {json.dumps(ready.known_mapping, ensure_ascii=False)}")


def demo_volcano(engine: FigureEngine, *, execute: bool) -> None:
    _banner("5. Generic Engine → transcriptomics.volcano")
    if not EXAMPLE_CSV.is_file():
        raise FileNotFoundError(f"缺少示例数据: {EXAMPLE_CSV}")

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EXAMPLE_CSV, OUT_DIR / "input.csv")

    answers = {
        "feature_id": "gene",
        "effect_size": "log2FoldChange",
        "significance": "padj",
        "data_file": "input.csv",
        "journal_style": "Nature",
        "log2FC_threshold": 1.0,
        "significance_threshold": 0.05,
    }
    print(f"work_dir : {OUT_DIR}")
    print(f"execute  : {execute}")
    print(f"answers  : {json.dumps(answers, ensure_ascii=False)}")

    result = engine.run(
        "transcriptomics.volcano",
        answers=answers,
        available_columns=["gene", "log2FoldChange", "padj", "pvalue"],
        user_request="请画一张 Nature 风格 RNA-seq 火山图",
        work_dir=OUT_DIR,
        data_source="input.csv",
        execute=execute,
    )

    print(f"\nstatus  : {result.status}")
    print(f"message : {result.message}")
    if result.spec:
        print("spec.figure_definition_id :", result.spec.get("figure_definition_id"))
        print("spec.data_mapping         :", result.spec.get("data_mapping"))
    if result.r_script_path:
        print(f"R script : {result.r_script_path}")
    if result.output_files:
        print("outputs :", ", ".join(result.output_files))
    if result.qc_report:
        print("QC      :", result.qc_report.get("status"))
    if result.log and execute:
        log_tail = result.log.strip().splitlines()[-8:]
        if log_tail:
            print("log (tail):")
            for line in log_tail:
                print("  ", line)

    # 方便演示时直接打开目录
    (OUT_DIR / "engine_result.json").write_text(
        result.model_dump_json(indent=2),
        encoding="utf-8",
    )
    print(f"\n完整结果已写入: {OUT_DIR / 'engine_result.json'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="SCIPlot Generic Figure Engine 演示")
    parser.add_argument(
        "--no-execute",
        action="store_true",
        help="只生成 Spec 与 R 脚本，不调用 Docker/R",
    )
    args = parser.parse_args()

    registry = FigureRegistry()
    engine = FigureEngine(registry=registry)

    demo_catalog(registry)
    demo_unknown(engine)
    demo_catalog_only(engine)
    demo_requirements(registry)
    demo_volcano(engine, execute=not args.no_execute)

    _banner("演示结束")
    print("下一步: 打开 examples/demo_generic_output/ 查看 figure.R / 图件 / QC_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

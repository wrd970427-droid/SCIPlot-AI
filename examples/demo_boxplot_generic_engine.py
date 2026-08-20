"""演示 Generic Figure Engine 第二个 Figure：basic_statistics.boxplot

用法（项目根目录）:

  python examples/demo_boxplot_generic_engine.py
  python examples/demo_boxplot_generic_engine.py --no-execute
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

EXAMPLE_CSV = ROOT / "examples" / "example_boxplot.csv"
OUT_DIR = ROOT / "examples" / "demo_boxplot_output"


def main() -> int:
    parser = argparse.ArgumentParser(description="Boxplot via Generic Figure Engine")
    parser.add_argument("--no-execute", action="store_true", help="Only Spec + R, skip R execution")
    args = parser.parse_args()

    registry = FigureRegistry()
    definition = registry.get_figure_definition("basic_statistics.boxplot")
    print("figure_id           :", definition.id)
    print("implementation      :", definition.implementation_status.value)
    print("data_schema_id      :", definition.data_schema_id)
    print("required_fields     :", [f.role for f in definition.required_fields])
    print("variants            :", definition.variants)

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EXAMPLE_CSV, OUT_DIR / "input.csv")

    answers = {
        "group": "group",
        "value": "value",
        "data_file": "input.csv",
        "journal_style": "Nature",
        "point_jitter": True,
        "point_size": 1.5,
        "alpha": 0.75,
        "line_width": 0.5,
        "variant": "boxplot",
    }

    engine = FigureEngine(registry=registry)
    result = engine.run(
        "basic_statistics.boxplot",
        answers=answers,
        available_columns=["group", "value", "sample_id"],
        user_request="比较 Control / Treatment / Disease 的连续值分布",
        work_dir=OUT_DIR,
        data_source="input.csv",
        execute=not args.no_execute,
    )

    print("status              :", result.status)
    print("message             :", result.message)
    if result.spec:
        print("data_mapping        :", result.spec.get("data_mapping"))
        print("visual_parameters   :", result.spec.get("visual_parameters"))
    if result.r_script_path:
        print("R script            :", result.r_script_path)
    if result.output_files:
        print("outputs             :", ", ".join(result.output_files))
    if result.qc_report:
        print("QC                  :", result.qc_report.get("status"))

    out_json = OUT_DIR / "engine_result.json"
    out_json.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print("engine_result.json  :", out_json)
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())

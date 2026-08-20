"""Load and validate the Scientific Figure Catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schemas.figure_definition import FigureDefinition

ROOT = Path(__file__).resolve().parents[1]  # knowledge/
CATALOG_DIR = Path(__file__).resolve().parent  # knowledge/scientific_figures/



def load_json(name: str) -> Any:
    return json.loads((CATALOG_DIR / name).read_text(encoding="utf-8"))


def load_catalog() -> list[FigureDefinition]:
    doc = load_json("catalog.json")
    return [FigureDefinition.model_validate(item) for item in doc["figures"]]


def load_taxonomy() -> dict[str, Any]:
    return load_json("taxonomy.json")


def load_data_schemas() -> dict[str, Any]:
    return load_json("data_schemas.json")


def load_package_registry() -> dict[str, Any]:
    return load_json("package_registry.json")


def load_composition_rules() -> dict[str, Any]:
    return load_json("composition_rules.json")


def load_source_registry() -> dict[str, Any]:
    return load_json("source_registry.json")

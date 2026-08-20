"""Load SCIPlot knowledge JSON. No Agent logic lives here."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = ROOT / "knowledge"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def load_volcano_rules(knowledge_root: str | None = None) -> dict[str, Any]:
    root = Path(knowledge_root) if knowledge_root else KNOWLEDGE_ROOT
    return _read_json(root / "figure_rules" / "volcano.json")


@lru_cache(maxsize=8)
def load_journal_styles(knowledge_root: str | None = None) -> dict[str, Any]:
    root = Path(knowledge_root) if knowledge_root else KNOWLEDGE_ROOT
    return _read_json(root / "journals" / "journal_styles.json")

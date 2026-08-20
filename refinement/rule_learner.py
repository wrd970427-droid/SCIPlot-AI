"""Persist user corrections as reusable refinement examples (no patient data)."""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEARNED = ROOT / "knowledge" / "learned_refinements.json"


class RuleLearner:
    """Append / recall correction examples for design-parameter NLU."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_LEARNED
        self._doc = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema_version": "0.1.0", "examples": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def reload(self) -> None:
        self._doc = self._load()

    @property
    def examples(self) -> list[dict[str, Any]]:
        return list(self._doc.get("examples", []))

    def match(self, user_request: str) -> dict[str, Any] | None:
        text = (user_request or "").strip()
        if not text:
            return None
        compact = re.sub(r"\s+", "", text).lower()
        best: dict[str, Any] | None = None
        best_score = 0.0
        for example in self.examples:
            phrases = [str(example.get("utterance", ""))] + list(example.get("utterance_aliases", []))
            for phrase in phrases:
                phrase = phrase.strip()
                if not phrase:
                    continue
                p = re.sub(r"\s+", "", phrase).lower()
                if compact == p:
                    return example
                # Soft overlap: shared character ratio for short Chinese corrections.
                overlap = len(set(compact) & set(p)) / max(len(set(p)), 1)
                if p in compact or compact in p:
                    score = 0.9 + 0.05 * min(len(p), 20) / 20
                else:
                    score = overlap
                if score > best_score and score >= 0.72:
                    best_score = score
                    best = example
        return best

    def learn_from_request(
        self,
        user_request: str,
        operations: list[dict[str, Any]],
        *,
        note: str = "",
    ) -> dict[str, Any] | None:
        """If the request looks like a correction, persist it for next time."""
        text = (user_request or "").strip()
        if not operations:
            return None
        if not self._looks_like_correction(text):
            return None
        # Avoid duplicates for nearly identical utterances.
        existing = self.match(text)
        if existing and existing.get("utterance") == text:
            return existing
        entry = {
            "id": f"learned_{uuid.uuid4().hex[:8]}",
            "utterance": text,
            "utterance_aliases": [],
            "operations": operations,
            "forbidden": self._infer_forbidden(text),
            "source": "user_correction",
            "note": note or "auto-learned from correction phrasing",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._doc.setdefault("examples", []).append(entry)
        self._save()
        return entry

    def learn_explicit(
        self,
        utterance: str,
        operations: list[dict[str, Any]],
        *,
        aliases: list[str] | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        entry = {
            "id": f"learned_{uuid.uuid4().hex[:8]}",
            "utterance": utterance.strip(),
            "utterance_aliases": list(aliases or []),
            "operations": operations,
            "forbidden": self._infer_forbidden(utterance),
            "source": "explicit",
            "note": note,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._doc.setdefault("examples", []).append(entry)
        self._save()
        return entry

    def prompt_examples(self, limit: int = 8) -> str:
        chunks: list[str] = []
        for example in self.examples[-limit:]:
            ops = json.dumps(example.get("operations", []), ensure_ascii=False)
            chunks.append(f"- “{example.get('utterance')}” → {ops}")
        return "\n".join(chunks)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _looks_like_correction(text: str) -> bool:
        markers = ("不是", "不要", "别", "别改成", "而不是", "而非", "instead of", "not ")
        return any(m in text.lower() if m.isascii() else m in text for m in markers)

    @staticmethod
    def _infer_forbidden(text: str) -> list[str]:
        forbidden: list[str] = []
        if re.search(r"不是.{0,6}全边框|不要.{0,6}全边框|别.{0,6}全边框|不是.{0,6}四周", text):
            forbidden.append("panel_border=full")
        return forbidden

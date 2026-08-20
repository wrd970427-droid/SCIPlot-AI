"""Map user-requested aesthetics onto table headers (no row values, no R)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

ROLE_PATTERNS: dict[str, tuple[str, ...]] = {
    "x": (
        r"([^,，;；]+?)\s*为\s*[Xx]轴",
        r"[Xx]轴\s*[:：是为]\s*([^,，;；]+)",
        r"(?:横轴|x\s*axis)\s*[:：是为]\s*([^,，;；]+)",
        r"\bx\s*=\s*([^\s,，]+)",
    ),
    "y": (
        r"([^,，;；]+?)\s*为\s*[Yy]轴",
        r"[Yy]轴\s*[:：是为]\s*([^,，;；]+)",
        r"(?:纵轴|y\s*axis)\s*[:：是为]\s*([^,，;；]+)",
        r"\by\s*=\s*([^\s,，]+)",
    ),
    "size": (
        r"([^,，;；]+?)\s*为点的大小",
        r"点的大小\s*[:：是为]\s*([^,，;；]+)",
        r"点大小\s*[:：是为]\s*([^,，;；]+)",
        r"(?:size|point size)\s*[:：是为=]\s*([^\s,，]+)",
    ),
    "group": (
        r"([^,，;；]+?)\s*为(?:分组|颜色|color|colour)",
        r"(?:分组|按组|color)\s*[:：是为]\s*([^,，;；]+)",
    ),
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (text or "").lower())


def match_column(token: str, columns: list[str]) -> str | None:
    needle = (token or "").strip().strip("`'\"“”")
    if not needle or not columns:
        return None
    lowered = {col.lower(): col for col in columns}
    if needle.lower() in lowered:
        return lowered[needle.lower()]
    n_needle = _norm(needle)
    if not n_needle:
        return None
    ranked: list[tuple[float, str]] = []
    for col in columns:
        n_col = _norm(col)
        score = 0.0
        if n_needle == n_col:
            score = 1.0
        elif n_needle in n_col or n_col in n_needle:
            score = 0.92
        else:
            score = SequenceMatcher(None, n_needle, n_col).ratio()
        if score >= 0.78:
            ranked.append((score, col))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], len(item[1])))
    return ranked[0][1]


def extract_role_tokens(prompt: str) -> dict[str, str]:
    found: dict[str, str] = {}
    text = prompt or ""
    for role, patterns in ROLE_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                token = match.group(1).strip().strip("`'\"“”")
                if token:
                    found[role] = token
                    break
    return found


def map_columns_from_request(
    prompt: str,
    columns: list[str],
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return role → actual column name."""
    mapping: dict[str, str] = {}
    candidates = dict(extract_role_tokens(prompt))
    for key, value in (extra or {}).items():
        if value:
            candidates[str(key)] = str(value)
    for role, token in candidates.items():
        hit = match_column(token, columns)
        if hit:
            mapping[role] = hit
    return mapping

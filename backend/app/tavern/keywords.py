"""Keyword list helpers stored as JSON text."""

from __future__ import annotations

import json


def dump_keywords(keywords: list[str] | None) -> str:
    """Normalize and serialize trigger keywords."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in keywords or []:
        text = str(item).strip()
        if not text:
            continue
        folded = text.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        cleaned.append(text[:80])
        if len(cleaned) >= 40:
            break
    return json.dumps(cleaned, ensure_ascii=False)


def load_keywords(raw: str | None) -> list[str]:
    """Read a stored keyword list. Invalid payloads become an empty list."""
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, str) and item.strip()]

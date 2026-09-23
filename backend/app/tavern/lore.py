"""Select world-book entries for a writing turn."""

from __future__ import annotations

from dataclasses import dataclass

from app.tavern.keywords import load_keywords


LORE_PACK_CHAR_BUDGET = 6000
CHARACTER_PACK_CHAR_BUDGET = 4000
_MIN_KEYWORD_LENGTH = 2


@dataclass(frozen=True)
class LoreCandidate:
    """Enabled lore row used by the selector."""

    name: str
    content: str
    order: int
    is_constant: bool
    keywords: tuple[str, ...]


def keyword_matches(keywords: list[str] | tuple[str, ...], haystack: str) -> bool:
    """Return whether any keyword appears in the writing task text."""
    folded = haystack.casefold()
    for keyword in keywords:
        needle = keyword.strip()
        if len(needle) < _MIN_KEYWORD_LENGTH:
            continue
        if needle.casefold() in folded:
            return True
    return False


def select_lore_entries(
    entries: list[LoreCandidate],
    haystack: str,
    *,
    budget: int = LORE_PACK_CHAR_BUDGET,
) -> list[LoreCandidate]:
    """Keep constant entries, then keyword hits, and stop at the character budget."""
    ordered = sorted(entries, key=lambda entry: entry.order)
    constants = [entry for entry in ordered if entry.is_constant and entry.content.strip()]
    triggered = [
        entry
        for entry in ordered
        if not entry.is_constant and entry.content.strip() and keyword_matches(entry.keywords, haystack)
    ]
    chosen: list[LoreCandidate] = []
    used = 0
    for entry in [*constants, *triggered]:
        text = entry.content.strip()
        remaining = budget - used
        if remaining <= 0:
            break
        if len(text) > remaining:
            if not chosen:
                chosen.append(
                    LoreCandidate(
                        name=entry.name,
                        content=text[:remaining],
                        order=entry.order,
                        is_constant=entry.is_constant,
                        keywords=entry.keywords,
                    )
                )
            break
        chosen.append(entry)
        used += len(text)
    return chosen


def render_setting_pack(
    *,
    characters: list[tuple[str, str]],
    lore_entries: list[LoreCandidate],
) -> str | None:
    """Render the system fragment inserted ahead of a writing turn."""
    character_lines = _render_characters(characters)
    lore_lines = [
        f"## {entry.name}\n{entry.content.strip()}"
        for entry in lore_entries
        if entry.content.strip()
    ]
    if not character_lines and not lore_lines:
        return None
    sections = ["<setting>"]
    if character_lines:
        sections.append("<characters>")
        sections.extend(character_lines)
        sections.append("</characters>")
    if lore_lines:
        sections.append("<world>")
        sections.extend(lore_lines)
        sections.append("</world>")
    sections.append("</setting>")
    return "\n".join(sections)


def _render_characters(characters: list[tuple[str, str]]) -> list[str]:
    lines: list[str] = []
    used = 0
    for name, description in characters:
        text = description.strip()
        if not text:
            continue
        remaining = CHARACTER_PACK_CHAR_BUDGET - used
        if remaining <= 0:
            break
        body = text if len(text) <= remaining else text[:remaining]
        lines.append(f"## {name}\n{body}")
        used += len(body)
    return lines


def keywords_from_json(raw: str | None) -> tuple[str, ...]:
    return tuple(load_keywords(raw))

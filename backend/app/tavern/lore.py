"""Select world-book entries for a writing turn.

A chapter turn gets a short card, not the whole book: the current instruction
and unfinished plan steps sit ahead of constant lore and keyword hits. That
keeps style and canon available without rereading every chapter.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.tavern.keywords import load_keywords


LORE_PACK_CHAR_BUDGET = 6000
CHARACTER_PACK_CHAR_BUDGET = 4000
TASK_REQUEST_CHAR_BUDGET = 600
TASK_TODO_ITEM_CHAR_BUDGET = 400
TASK_TODO_TOTAL_CHAR_BUDGET = 1200
MAX_OPEN_TODOS = 3
_MIN_KEYWORD_LENGTH = 2

# Order matches a writing turn: immediate task, then style already injected
# elsewhere, then this canon pack. Later material must not override earlier.
WRITING_PRIORITY = """<writing_priority>
写这一轮时按下面的顺序取舍，后面的不能覆盖前面的：
1. 用户当次指令，以及「当前任务」里未完成的计划步骤。它决定这一轮写什么、改什么、审什么。
2. 已启用的文风规则和技能。它们决定怎么写，不决定剧情。
3. 本段设定。常驻条目优先于关键词命中；没命中的条目不要假设它存在。
4. 近期章节和摘要只用于衔接。不要为了这一轮重读或复述整本书。
设定里没有的专有事实不要现编。任务没要求的剧情不要加。
</writing_priority>"""


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


def compact_open_todos(
    lines: list[str],
    *,
    item_budget: int = TASK_TODO_ITEM_CHAR_BUDGET,
    total_budget: int = TASK_TODO_TOTAL_CHAR_BUDGET,
    limit: int = MAX_OPEN_TODOS,
) -> list[str]:
    """Keep a few unfinished plan steps so the task card stays smaller than the book."""
    kept: list[str] = []
    used = 0
    for raw in lines:
        if len(kept) >= limit or used >= total_budget:
            break
        text = _clip(raw, item_budget)
        if not text:
            continue
        kept.append(text)
        used += len(text)
    return kept


def render_chapter_task(*, user_request: str, open_todos: list[str]) -> str | None:
    """Render the immediate task. Empty when this turn has nothing to steer."""
    request = _clip(user_request, TASK_REQUEST_CHAR_BUDGET)
    todos = compact_open_todos(open_todos)
    if not request and not todos:
        return None
    lines = [
        "<chapter_task>",
        "这一轮只处理下面这些事。它优先于设定和旧章节。",
    ]
    if request:
        lines.append("## 用户当次指令")
        lines.append(request)
    if todos:
        lines.append("## 未完成的计划步骤")
        lines.append("先做进行中的那一步。不要提前做后面的步骤，也不要重做已完成的步骤。")
        lines.extend(f"{index}. {item}" for index, item in enumerate(todos, start=1))
    lines.append("</chapter_task>")
    return "\n".join(lines)


def render_writing_turn(
    *,
    characters: list[tuple[str, str]],
    lore_entries: list[LoreCandidate],
    user_request: str = "",
    open_todos: list[str] | None = None,
) -> str | None:
    """Render task plus canon. Returns None when both sides are empty."""
    task = render_chapter_task(user_request=user_request, open_todos=open_todos or [])
    setting = render_setting_pack(characters=characters, lore_entries=lore_entries)
    if task is None and setting is None:
        return None
    sections = ["<writing_context>", WRITING_PRIORITY]
    if task is not None:
        sections.append(task)
    if setting is not None:
        sections.append(setting)
    sections.append("</writing_context>")
    return "\n".join(sections)


def _clip(text: str, budget: int) -> str:
    stripped = text.strip()
    if budget <= 0 or not stripped:
        return ""
    if len(stripped) <= budget:
        return stripped
    if budget <= 3:
        return stripped[:budget]
    return stripped[: budget - 3].rstrip() + "..."


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

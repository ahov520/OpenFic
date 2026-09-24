# -*- coding: utf-8 -*-
"""章节旁注。

旁注贴在作者选中的原句上，单独存放，不写进章节正文。
字数统计和导出只看正文，因此旁注文字不能进入 content。
"""

from __future__ import annotations

from dataclasses import dataclass

ANCHOR_MAX_LENGTH = 1000
BODY_MAX_LENGTH = 800
CONTEXT_MAX_LENGTH = 40
STATUSES = ("open", "struck")
DEFAULT_STATUS = "open"
EMPTY_SELECTION_MESSAGE = "请先选中要记下的文字"
EMPTY_BODY_MESSAGE = "旁注不能为空"
ANCHOR_TOO_LONG_MESSAGE = "选中的文字过长，请收短到一句话或一小段"
BODY_TOO_LONG_MESSAGE = "旁注过长"

# 给当前章上下文的单独一节。不放进 content。
MARGIN_NOTE_NOTICE = (
    "作者旁注，贴在选中的原句旁边。这不是正文，不计入字数，也不要写进章节。"
)
AGENT_NOTE_LIMIT = 6
AGENT_ANCHOR_LIMIT = 120
AGENT_BODY_LIMIT = 160


@dataclass(frozen=True)
class AnchorHit:
    """原句在当前正文里的位置。对不齐时不给出可高亮的区间。"""

    aligned: bool
    start: int | None
    end: int | None


def _newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def normalize_anchor(value: str | None) -> str:
    """保存选中的原文。空选区直接拒绝，不静默丢掉。"""
    text = _newlines(value or "")
    if not text.strip():
        raise ValueError(EMPTY_SELECTION_MESSAGE)
    if len(text) > ANCHOR_MAX_LENGTH:
        raise ValueError(ANCHOR_TOO_LONG_MESSAGE)
    return text


def normalize_body(value: str | None) -> str:
    text = _newlines(value or "").strip()
    if not text:
        raise ValueError(EMPTY_BODY_MESSAGE)
    if len(text) > BODY_MAX_LENGTH:
        raise ValueError(BODY_TOO_LONG_MESSAGE)
    return text


def normalize_context(value: str | None, *, keep_end: bool) -> str:
    """选区两侧的一小段原文，只用来区分重复的句子。"""
    text = _newlines(value or "")
    if len(text) <= CONTEXT_MAX_LENGTH:
        return text
    if keep_end:
        return text[-CONTEXT_MAX_LENGTH:]
    return text[:CONTEXT_MAX_LENGTH]


def normalize_status(value: str | None) -> str:
    if value not in STATUSES:
        raise ValueError("旁注状态无效")
    return value


def locate_anchor(
    content: str,
    anchor: str,
    before: str = "",
    after: str = "",
) -> AnchorHit:
    """在正文里找旁注锚住的原句。

    原句只出现一次时，周围文字改了也能找到。
    原句重复时，只有保存下来的前后文仍能唯一对上才算对齐。
    对不上或无法唯一确定时，不返回位置，避免高亮到另一句。
    """
    if not anchor:
        return AnchorHit(False, None, None)

    starts: list[int] = []
    search_from = 0
    while True:
        found = content.find(anchor, search_from)
        if found < 0:
            break
        starts.append(found)
        search_from = found + 1

    if not starts:
        return AnchorHit(False, None, None)

    if len(starts) == 1:
        start = starts[0]
        return AnchorHit(True, start, start + len(anchor))

    confident = [index for index in starts if _context_matches(content, anchor, before, after, index)]
    if len(confident) != 1:
        return AnchorHit(False, None, None)
    start = confident[0]
    return AnchorHit(True, start, start + len(anchor))


def _context_matches(
    content: str,
    anchor: str,
    before: str,
    after: str,
    index: int,
) -> bool:
    if before:
        actual_before = content[max(0, index - len(before)) : index]
        if actual_before != before:
            return False
    if after:
        actual_after = content[index + len(anchor) : index + len(anchor) + len(after)]
        if actual_after != after:
            return False
    return True


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def agent_margin_payload(notes: list[object]) -> dict[str, object] | None:
    """未划掉的旁注。没有则不占上下文。划掉的不带进去。"""
    open_notes = [
        note
        for note in notes
        if getattr(note, "status", None) == "open"
        and isinstance(getattr(note, "anchor_text", None), str)
        and isinstance(getattr(note, "body", None), str)
    ]
    if not open_notes:
        return None
    shown = open_notes[:AGENT_NOTE_LIMIT]
    items: list[dict[str, str]] = []
    for note in shown:
        anchor_text = getattr(note, "anchor_text", "")
        body = getattr(note, "body", "")
        if not isinstance(anchor_text, str) or not isinstance(body, str):
            continue
        items.append(
            {
                "anchor": _clip(anchor_text, AGENT_ANCHOR_LIMIT),
                "note": _clip(body, AGENT_BODY_LIMIT),
            }
        )
    if not items:
        return None
    payload: dict[str, object] = {
        "notice": MARGIN_NOTE_NOTICE,
        "notes": items,
    }
    omitted = len(open_notes) - len(shown)
    if omitted:
        payload["omitted"] = omitted
    return payload

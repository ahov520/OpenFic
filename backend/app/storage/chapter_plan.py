# -*- coding: utf-8 -*-
"""作者章节卡片：梗概与写作状态。

梗概是作者在写正文之前放在章节上的计划，不是模型生成的章节摘要。
"""

from __future__ import annotations

from app.storage.chapter_length import read_word_count_target

WRITING_STATUSES = ("idea", "drafting", "revising", "done")
DEFAULT_WRITING_STATUS = "idea"
SYNOPSIS_MAX_LENGTH = 2000
CATALOG_SYNOPSIS_LIMIT = 160


def normalize_writing_status(value: str | None) -> str:
    """校验写作状态。空值视为构思。"""
    if value is None or value == "":
        return DEFAULT_WRITING_STATUS
    if value not in WRITING_STATUSES:
        raise ValueError("写作状态无效")
    return value


def normalize_synopsis(value: str | None) -> str:
    """规范化梗概换行，并限制长度。"""
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > SYNOPSIS_MAX_LENGTH:
        raise ValueError(f"梗概超出 {SYNOPSIS_MAX_LENGTH} 字限制")
    return text


def read_chapter_plan(chapter: object) -> tuple[str, str]:
    """从章节对象读取梗概和写作状态，缺省时给出安全默认值。"""
    raw_synopsis = getattr(chapter, "synopsis", "")
    synopsis = raw_synopsis if isinstance(raw_synopsis, str) else ""
    raw_status = getattr(chapter, "writing_status", None)
    status = (
        raw_status
        if isinstance(raw_status, str) and raw_status in WRITING_STATUSES
        else DEFAULT_WRITING_STATUS
    )
    return synopsis, status


def latest_plan_fields(chapter: object) -> dict[str, str | int]:
    """当前章节上下文里带上作者计划，供写正文时遵守。"""
    synopsis, status = read_chapter_plan(chapter)
    fields: dict[str, str | int] = {"writing_status": status}
    stripped = synopsis.strip()
    if stripped:
        fields["author_synopsis"] = stripped
    target = read_word_count_target(chapter)
    if target is not None:
        fields["word_count_target"] = target
    return fields


def catalog_plan_fields(chapter: object) -> dict[str, str]:
    """目录里只放状态和截断后的梗概，避免把整本计划塞满上下文。"""
    synopsis, status = read_chapter_plan(chapter)
    fields = {"writing_status": status}
    stripped = synopsis.strip()
    if not stripped:
        return fields
    if len(stripped) > CATALOG_SYNOPSIS_LIMIT:
        stripped = stripped[: CATALOG_SYNOPSIS_LIMIT - 1] + "…"
    fields["author_synopsis"] = stripped
    return fields

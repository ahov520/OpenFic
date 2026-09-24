# -*- coding: utf-8 -*-
"""上一章结尾。从已有正文按字数口径截末尾，不另存，也不写入本章。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.memory.chapter.sequence import global_reading_sequence
from app.storage.models.chapter import Chapter
from app.storage.repos import chapter_repo, volume_repo

# 与 chapter_service._count_words 相同：汉字一字，其余非空白片段一词。
PREVIOUS_ENDING_UNIT_LIMIT = 100
PREVIOUS_ENDING_NOTICE = (
    "这是上一章的结尾，只用来接上停住的那一句。"
    "它不是本章正文，不要写进本章，也不计入本章字数。"
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True)
class PreviousChapterEnding:
    """阅读顺序中紧挨着的上一章，及其结尾摘录。"""

    chapter_id: str
    title: str
    excerpt: str


def count_units(text: str) -> int:
    """与章节字数回退口径相同的计数。"""
    if not text:
        return 0
    chinese_count = len(_CJK_RE.findall(text))
    without_chinese = _CJK_RE.sub(" ", text)
    english_count = sum(1 for word in without_chinese.split() if word.strip())
    return chinese_count + english_count


def _unit_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    index = 0
    length = len(text)
    while index < length:
        if _CJK_RE.match(text, index):
            spans.append((index, index + 1))
            index += 1
            continue
        if text[index].isspace():
            index += 1
            continue
        end = index + 1
        while (
            end < length
            and not text[end].isspace()
            and _CJK_RE.match(text, end) is None
        ):
            end += 1
        spans.append((index, end))
        index = end
    return spans


def tail_by_units(text: str, limit: int = PREVIOUS_ENDING_UNIT_LIMIT) -> str | None:
    """取纯文本末尾若干计数单位。没有可计的正文时返回 None。"""
    if limit <= 0 or not text:
        return None
    spans = _unit_spans(text)
    if not spans:
        return None
    if len(spans) <= limit:
        excerpt = text.strip()
    else:
        excerpt = text[spans[-limit][0] :].strip()
    if not excerpt or count_units(excerpt) == 0:
        return None
    return excerpt


def previous_ending_for_agent(chapter: Chapter | None) -> dict[str, str] | None:
    """给当前章上下文的单独字段。没有上一章正文时不放。"""
    if chapter is None:
        return None
    excerpt = tail_by_units(chapter.content or "")
    if excerpt is None:
        return None
    return {
        "notice": PREVIOUS_ENDING_NOTICE,
        "chapter_id": chapter.id,
        "title": chapter.title,
        "excerpt": excerpt,
    }


async def load_previous_chapter_ending(
    session: AsyncSession, chapter_id: str
) -> PreviousChapterEnding | None:
    """按卷序和卷内序找紧邻的上一章。第一章或上一章没有正文时不返回摘录。"""
    current = await chapter_repo.get_by_id(session, chapter_id)
    if current is None:
        raise NotFoundError("章节不存在")

    chapters = await chapter_repo.list_metadata_by_project(session, current.project_id)
    volumes = await volume_repo.list_by_project(session, current.project_id)
    sequence = global_reading_sequence(chapters, volumes)
    index = next(
        (i for i, (_, chapter) in enumerate(sequence) if chapter.id == chapter_id), None
    )
    if index is None or index == 0:
        return None

    previous = await chapter_repo.get_by_id(session, sequence[index - 1][1].id)
    if previous is None:
        return None
    excerpt = tail_by_units(previous.content)
    if excerpt is None:
        return None
    return PreviousChapterEnding(
        chapter_id=previous.id,
        title=previous.title,
        excerpt=excerpt,
    )

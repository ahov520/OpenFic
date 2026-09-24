# -*- coding: utf-8 -*-
"""章节旁注数据访问。"""

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.storage.margin_notes import DEFAULT_STATUS
from app.storage.models.chapter import Chapter
from app.storage.models.margin_note import ChapterMarginNote


async def create(session: AsyncSession, note: ChapterMarginNote) -> ChapterMarginNote:
    session.add(note)
    await session.flush()
    await session.refresh(note)
    return note


async def get_by_id(session: AsyncSession, note_id: str) -> ChapterMarginNote | None:
    result = await session.execute(
        select(ChapterMarginNote).where(col(ChapterMarginNote.id) == note_id)
    )
    return result.scalar_one_or_none()


async def count_open_by_project(
    session: AsyncSession, project_id: str
) -> dict[str, int]:
    """各章未划掉的旁注条数。一次聚合，没有未处理旁注的章不出现。"""
    result = await session.execute(
        select(col(ChapterMarginNote.chapter_id), func.count(col(ChapterMarginNote.id)))
        .where(col(ChapterMarginNote.project_id) == project_id)
        .where(col(ChapterMarginNote.status) == DEFAULT_STATUS)
        .group_by(col(ChapterMarginNote.chapter_id))
    )
    return {chapter_id: int(count) for chapter_id, count in result.all()}


async def count_open_by_chapter_ids(
    session: AsyncSession, chapter_ids: list[str]
) -> dict[str, int]:
    """指定章节里未划掉的旁注条数。空列表不查库。"""
    if not chapter_ids:
        return {}
    result = await session.execute(
        select(col(ChapterMarginNote.chapter_id), func.count(col(ChapterMarginNote.id)))
        .where(col(ChapterMarginNote.chapter_id).in_(chapter_ids))
        .where(col(ChapterMarginNote.status) == DEFAULT_STATUS)
        .group_by(col(ChapterMarginNote.chapter_id))
    )
    return {chapter_id: int(count) for chapter_id, count in result.all()}


async def list_by_chapter(
    session: AsyncSession, chapter_id: str
) -> list[ChapterMarginNote]:
    result = await session.execute(
        select(ChapterMarginNote)
        .where(col(ChapterMarginNote.chapter_id) == chapter_id)
        .order_by(
            col(ChapterMarginNote.created_at).asc(), col(ChapterMarginNote.id).asc()
        )
    )
    return list(result.scalars().all())


async def save(session: AsyncSession, note: ChapterMarginNote) -> ChapterMarginNote:
    session.add(note)
    await session.flush()
    await session.refresh(note)
    return note


async def delete(session: AsyncSession, note: ChapterMarginNote) -> None:
    await session.delete(note)
    await session.flush()


async def delete_by_chapter_ids(session: AsyncSession, chapter_ids: list[str]) -> None:
    if not chapter_ids:
        return
    await session.execute(
        sql_delete(ChapterMarginNote).where(
            col(ChapterMarginNote.chapter_id).in_(chapter_ids)
        )
    )
    await session.flush()


async def delete_by_project(session: AsyncSession, project_id: str) -> None:
    chapter_ids = select(Chapter.id).where(col(Chapter.project_id) == project_id)
    await session.execute(
        sql_delete(ChapterMarginNote).where(
            col(ChapterMarginNote.chapter_id).in_(chapter_ids)
        )
    )
    await session.flush()

# -*- coding: utf-8 -*-
"""章节旁注数据访问。"""

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.storage.models.chapter import Chapter
from app.storage.models.margin_note import ChapterMarginNote
from app.storage.models.volume import Volume


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


async def list_open_by_project(
    session: AsyncSession, project_id: str
) -> list[tuple[ChapterMarginNote, str]]:
    """全书未划掉的旁注，一次取出。顺序是卷序、卷内章节序，章内再按创建时间。"""
    result = await session.execute(
        select(ChapterMarginNote, col(Chapter.title))
        .join(Chapter, col(Chapter.id) == col(ChapterMarginNote.chapter_id))
        .join(Volume, col(Volume.id) == col(Chapter.volume_id))
        .where(
            col(ChapterMarginNote.project_id) == project_id,
            col(ChapterMarginNote.status) == "open",
        )
        .order_by(
            col(Volume.order).asc(),
            col(Chapter.order).asc(),
            col(ChapterMarginNote.created_at).asc(),
            col(ChapterMarginNote.id).asc(),
        )
    )
    return [(note, title) for note, title in result.all()]


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

# -*- coding: utf-8 -*-
"""情节线节拍数据访问。"""

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.storage.models.plot_thread import PlotBeat


async def create(session: AsyncSession, beat: PlotBeat) -> PlotBeat:
    session.add(beat)
    await session.flush()
    await session.refresh(beat)
    return beat


async def get_by_id(session: AsyncSession, beat_id: str) -> PlotBeat | None:
    result = await session.execute(select(PlotBeat).where(col(PlotBeat.id) == beat_id))
    return result.scalar_one_or_none()


async def get_by_thread_chapter(
    session: AsyncSession,
    thread_id: str,
    chapter_id: str,
) -> PlotBeat | None:
    result = await session.execute(
        select(PlotBeat).where(
            col(PlotBeat.thread_id) == thread_id,
            col(PlotBeat.chapter_id) == chapter_id,
        )
    )
    return result.scalar_one_or_none()


async def list_by_project(session: AsyncSession, project_id: str) -> list[PlotBeat]:
    result = await session.execute(
        select(PlotBeat)
        .where(col(PlotBeat.project_id) == project_id)
        .order_by(col(PlotBeat.created_at).asc())
    )
    return list(result.scalars().all())


async def list_by_thread(session: AsyncSession, thread_id: str) -> list[PlotBeat]:
    result = await session.execute(
        select(PlotBeat).where(col(PlotBeat.thread_id) == thread_id)
    )
    return list(result.scalars().all())


async def save(session: AsyncSession, beat: PlotBeat) -> PlotBeat:
    session.add(beat)
    await session.flush()
    await session.refresh(beat)
    return beat


async def delete(session: AsyncSession, beat: PlotBeat) -> None:
    await session.delete(beat)
    await session.flush()


async def delete_by_thread(session: AsyncSession, thread_id: str) -> None:
    await session.execute(
        sql_delete(PlotBeat).where(col(PlotBeat.thread_id) == thread_id)
    )
    await session.flush()


async def delete_by_chapter_ids(session: AsyncSession, chapter_ids: list[str]) -> None:
    if not chapter_ids:
        return
    await session.execute(
        sql_delete(PlotBeat).where(col(PlotBeat.chapter_id).in_(chapter_ids))
    )
    await session.flush()


async def delete_by_project(session: AsyncSession, project_id: str) -> None:
    await session.execute(
        sql_delete(PlotBeat).where(col(PlotBeat.project_id) == project_id)
    )
    await session.flush()

# -*- coding: utf-8 -*-
"""情节线数据访问。"""

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.storage.models.plot_thread import PlotThread


async def create(session: AsyncSession, thread: PlotThread) -> PlotThread:
    session.add(thread)
    await session.flush()
    await session.refresh(thread)
    return thread


async def get_by_id(session: AsyncSession, thread_id: str) -> PlotThread | None:
    result = await session.execute(
        select(PlotThread).where(col(PlotThread.id) == thread_id)
    )
    return result.scalar_one_or_none()


async def list_by_project(session: AsyncSession, project_id: str) -> list[PlotThread]:
    result = await session.execute(
        select(PlotThread)
        .where(col(PlotThread.project_id) == project_id)
        .order_by(col(PlotThread.sort_order).asc(), col(PlotThread.created_at).asc())
    )
    return list(result.scalars().all())


async def max_sort_order(session: AsyncSession, project_id: str) -> int:
    result = await session.execute(
        select(func.max(PlotThread.sort_order)).where(
            col(PlotThread.project_id) == project_id
        )
    )
    value = result.scalar_one()
    return int(value or 0)


async def save(session: AsyncSession, thread: PlotThread) -> PlotThread:
    session.add(thread)
    await session.flush()
    await session.refresh(thread)
    return thread


async def delete(session: AsyncSession, thread: PlotThread) -> None:
    await session.delete(thread)
    await session.flush()


async def delete_by_project(session: AsyncSession, project_id: str) -> None:
    await session.execute(
        sql_delete(PlotThread).where(col(PlotThread.project_id) == project_id)
    )
    await session.flush()

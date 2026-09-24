# -*- coding: utf-8 -*-
"""情节线业务：创建、挂到章节，以及断线视图。"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.memory.chapter.sequence import global_order_index
from app.storage.models.chapter import Chapter
from app.storage.models.plot_thread import PlotBeat, PlotThread
from app.storage.models.volume import Volume
from app.storage.plot_threads import (
    ChapterSpot,
    ThreadAssessment,
    agent_plot_context,
    assess_plot_threads,
    normalize_beat_kind,
    normalize_intent,
    normalize_note,
    normalize_thread_name,
    normalize_thread_status,
)
from app.storage.repos import (
    chapter_repo,
    plot_beat_repo,
    plot_thread_repo,
    project_repo,
    volume_repo,
)


@dataclass(frozen=True)
class BoardThread:
    """一条线的存储记录和断线判断。"""

    thread: PlotThread
    assessment: ThreadAssessment


@dataclass(frozen=True)
class PlotBoard:
    """全书情节线，以及挂节拍时可选的章节。"""

    threads: list[BoardThread]
    chapters: list[ChapterSpot]
    beats: dict[str, PlotBeat]


async def create_thread(
    session: AsyncSession,
    project_id: str,
    *,
    name: str,
    intent: str = "",
    status: str | None = None,
) -> PlotThread:
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")
    thread = PlotThread(
        project_id=project_id,
        name=normalize_thread_name(name),
        intent=normalize_intent(intent),
        status=normalize_thread_status(status),
        sort_order=await plot_thread_repo.max_sort_order(session, project_id) + 1,
    )
    return await plot_thread_repo.create(session, thread)


async def update_thread(
    session: AsyncSession,
    thread_id: str,
    *,
    name: str | None = None,
    intent: str | None = None,
    status: str | None = None,
) -> PlotThread:
    thread = await _get_thread(session, thread_id)
    if name is not None:
        thread.name = normalize_thread_name(name)
    if intent is not None:
        thread.intent = normalize_intent(intent)
    if status is not None:
        thread.status = normalize_thread_status(status)
    thread.updated_at = datetime.now(UTC)
    return await plot_thread_repo.save(session, thread)


async def delete_thread(session: AsyncSession, thread_id: str) -> None:
    thread = await _get_thread(session, thread_id)
    await plot_beat_repo.delete_by_thread(session, thread.id)
    await plot_thread_repo.delete(session, thread)


async def create_beat(
    session: AsyncSession,
    thread_id: str,
    *,
    chapter_id: str,
    kind: str,
    note: str = "",
) -> PlotBeat:
    thread = await _get_thread(session, thread_id)
    await _require_chapter(session, thread.project_id, chapter_id)
    existing = await plot_beat_repo.get_by_thread_chapter(
        session, thread.id, chapter_id
    )
    if existing is not None:
        raise ConflictError("这一章已经记过这条情节线")
    beat = PlotBeat(
        project_id=thread.project_id,
        thread_id=thread.id,
        chapter_id=chapter_id,
        kind=normalize_beat_kind(kind),
        note=normalize_note(note),
    )
    return await plot_beat_repo.create(session, beat)


async def update_beat(
    session: AsyncSession,
    beat_id: str,
    *,
    chapter_id: str | None = None,
    kind: str | None = None,
    note: str | None = None,
) -> PlotBeat:
    beat = await _get_beat(session, beat_id)
    if chapter_id is not None and chapter_id != beat.chapter_id:
        await _require_chapter(session, beat.project_id, chapter_id)
        existing = await plot_beat_repo.get_by_thread_chapter(
            session, beat.thread_id, chapter_id
        )
        if existing is not None and existing.id != beat.id:
            raise ConflictError("这一章已经记过这条情节线")
        beat.chapter_id = chapter_id
    if kind is not None:
        beat.kind = normalize_beat_kind(kind)
    if note is not None:
        beat.note = normalize_note(note)
    beat.updated_at = datetime.now(UTC)
    return await plot_beat_repo.save(session, beat)


async def delete_beat(session: AsyncSession, beat_id: str) -> None:
    beat = await _get_beat(session, beat_id)
    await plot_beat_repo.delete(session, beat)


async def get_board(session: AsyncSession, project_id: str) -> PlotBoard:
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")
    threads = await plot_thread_repo.list_by_project(session, project_id)
    beats = await plot_beat_repo.list_by_project(session, project_id)
    chapters, spots = await _chapter_spots(session, project_id)
    assessments = _assess(threads, beats, spots)
    by_id = {item.id: item for item in assessments}
    return PlotBoard(
        threads=[
            BoardThread(thread=thread, assessment=by_id[thread.id])
            for thread in threads
            if thread.id in by_id
        ],
        chapters=spots,
        beats={beat.id: beat for beat in beats},
    )


async def context_for_chapter(
    session: AsyncSession,
    project_id: str,
    chapter_id: str,
    *,
    chapters: list[Chapter] | None = None,
    volumes: list[Volume] | None = None,
) -> dict[str, object] | None:
    """给当前章的 Agent 上下文一份短计划。没有相关线时返回空。"""
    threads = await plot_thread_repo.list_by_project(session, project_id)
    if not threads:
        return None
    beats = await plot_beat_repo.list_by_project(session, project_id)
    if chapters is None or volumes is None:
        _chapters, spots = await _chapter_spots(session, project_id)
    else:
        spots = _spots_from(chapters, volumes)
    current = next((spot for spot in spots if spot.id == chapter_id), None)
    if current is None:
        return None
    return agent_plot_context(
        current_chapter_id=chapter_id,
        current_global_order=current.global_order,
        assessments=_assess(threads, beats, spots),
        reading_order=[spot.id for spot in spots],
    )


def _assess(
    threads: list[PlotThread],
    beats: list[PlotBeat],
    spots: list[ChapterSpot],
) -> list[ThreadAssessment]:
    return assess_plot_threads(
        [
            (thread.id, thread.name, thread.intent, thread.status, thread.sort_order)
            for thread in threads
        ],
        [
            (beat.id, beat.thread_id, beat.chapter_id, beat.kind, beat.note)
            for beat in beats
        ],
        spots,
    )


async def _chapter_spots(
    session: AsyncSession,
    project_id: str,
) -> tuple[list[Chapter], list[ChapterSpot]]:
    chapters = await chapter_repo.list_metadata_by_project(session, project_id)
    volumes = await volume_repo.list_by_project(session, project_id)
    return chapters, _spots_from(chapters, volumes)


def _spots_from(chapters: list[Chapter], volumes: list[Volume]) -> list[ChapterSpot]:
    order_map = global_order_index(chapters, volumes)
    volume_titles = {volume.id: volume.title for volume in volumes}
    spots = [
        ChapterSpot(
            id=chapter.id,
            title=chapter.title,
            global_order=order_map[chapter.id],
            volume_title=volume_titles.get(chapter.volume_id, ""),
        )
        for chapter in chapters
        if chapter.id in order_map
    ]
    spots.sort(key=lambda spot: spot.global_order)
    return spots


async def _get_thread(session: AsyncSession, thread_id: str) -> PlotThread:
    thread = await plot_thread_repo.get_by_id(session, thread_id)
    if thread is None:
        raise NotFoundError(f"情节线不存在: {thread_id}")
    return thread


async def _get_beat(session: AsyncSession, beat_id: str) -> PlotBeat:
    beat = await plot_beat_repo.get_by_id(session, beat_id)
    if beat is None:
        raise NotFoundError(f"节拍不存在: {beat_id}")
    return beat


async def _require_chapter(
    session: AsyncSession, project_id: str, chapter_id: str
) -> Chapter:
    chapter = await chapter_repo.get_by_id(session, chapter_id)
    if chapter is None or chapter.project_id != project_id:
        raise NotFoundError(f"章节不存在: {chapter_id}")
    return chapter

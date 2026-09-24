# -*- coding: utf-8 -*-
"""情节线 API。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.plot_thread import (
    BeatKind,
    PlotBeatCreate,
    PlotBeatResponse,
    PlotBeatUpdate,
    PlotBoardResponse,
    PlotChapterOption,
    PlotIssue,
    PlotThreadCreate,
    PlotThreadResponse,
    PlotThreadUpdate,
    ThreadStatus,
)
from app.background.jobs import service as background_service
from app.core.errors import ConflictError, NotFoundError
from app.storage.database import get_session
from app.storage.models.plot_thread import PlotBeat
from app.storage.plot_threads import BeatSpot
from app.storage.services import plot_thread_service
from app.storage.services.plot_thread_service import BoardThread

router = APIRouter(tags=["plot-threads"])


def _beat_kind(value: str) -> BeatKind:
    return cast(BeatKind, value)


def _thread_status(value: str) -> ThreadStatus:
    return cast(ThreadStatus, value)


def _issues(values: tuple[str, ...]) -> list[PlotIssue]:
    return [cast(PlotIssue, value) for value in values]


def _beat_response(beat: PlotBeat, spot: BeatSpot) -> PlotBeatResponse:
    return PlotBeatResponse(
        id=beat.id,
        thread_id=beat.thread_id,
        chapter_id=beat.chapter_id,
        chapter_title=spot.chapter_title,
        volume_title=spot.volume_title,
        global_order=spot.global_order,
        kind=_beat_kind(spot.kind),
        note=beat.note,
        created_at=beat.created_at,
        updated_at=beat.updated_at,
    )


def _thread_response(
    item: BoardThread, beats: dict[str, PlotBeat]
) -> PlotThreadResponse:
    assessment = item.assessment
    last = assessment.last_beat
    return PlotThreadResponse(
        id=item.thread.id,
        project_id=item.thread.project_id,
        name=item.thread.name,
        intent=item.thread.intent,
        status=_thread_status(item.thread.status),
        sort_order=item.thread.sort_order,
        issues=_issues(assessment.issues),
        has_plant=assessment.has_plant,
        has_payoff=assessment.has_payoff,
        last_chapter_id=last.chapter_id if last else None,
        last_chapter_title=last.chapter_title if last else None,
        last_global_order=last.global_order if last else None,
        last_kind=_beat_kind(last.kind) if last else None,
        beats=[
            _beat_response(beats[spot.id], spot)
            for spot in assessment.beats
            if spot.id in beats
        ],
        created_at=item.thread.created_at,
        updated_at=item.thread.updated_at,
    )


@router.get(
    "/projects/{project_id}/plot-threads",
    response_model=PlotBoardResponse,
    summary="获取情节线总览",
)
async def list_plot_threads(
    project_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlotBoardResponse:
    try:
        board = await plot_thread_service.get_board(session, project_id)
        return PlotBoardResponse(
            threads=[_thread_response(item, board.beats) for item in board.threads],
            chapters=[
                PlotChapterOption(
                    id=chapter.id,
                    title=chapter.title,
                    global_order=chapter.global_order,
                    volume_title=chapter.volume_title,
                )
                for chapter in board.chapters
            ],
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/projects/{project_id}/plot-threads",
    response_model=PlotThreadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建情节线",
)
async def create_plot_thread(
    project_id: str,
    data: PlotThreadCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlotThreadResponse:
    try:
        logger.info(f"创建情节线: project_id={project_id}, name={data.name}")
        thread = await plot_thread_service.create_thread(
            session,
            project_id,
            name=data.name,
            intent=data.intent,
            status=data.status,
        )
        await background_service.commit_and_notify(session)
        return await _reload_thread(session, project_id, thread.id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.patch(
    "/plot-threads/{thread_id}",
    response_model=PlotThreadResponse,
    summary="更新情节线",
)
async def update_plot_thread(
    thread_id: str,
    data: PlotThreadUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlotThreadResponse:
    try:
        thread = await plot_thread_service.update_thread(
            session,
            thread_id,
            name=data.name,
            intent=data.intent,
            status=data.status,
        )
        await background_service.commit_and_notify(session)
        return await _reload_thread(session, thread.project_id, thread.id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.delete(
    "/plot-threads/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除情节线",
)
async def delete_plot_thread(
    thread_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    try:
        await plot_thread_service.delete_thread(session, thread_id)
        await background_service.commit_and_notify(session)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/plot-threads/{thread_id}/beats",
    response_model=PlotThreadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="把情节线挂到章节",
)
async def create_plot_beat(
    thread_id: str,
    data: PlotBeatCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlotThreadResponse:
    try:
        beat = await plot_thread_service.create_beat(
            session,
            thread_id,
            chapter_id=data.chapter_id,
            kind=data.kind,
            note=data.note,
        )
        await background_service.commit_and_notify(session)
        return await _reload_thread(session, beat.project_id, beat.thread_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.patch(
    "/plot-beats/{beat_id}",
    response_model=PlotThreadResponse,
    summary="更新章节节拍",
)
async def update_plot_beat(
    beat_id: str,
    data: PlotBeatUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlotThreadResponse:
    try:
        beat = await plot_thread_service.update_beat(
            session,
            beat_id,
            chapter_id=data.chapter_id,
            kind=data.kind,
            note=data.note,
        )
        await background_service.commit_and_notify(session)
        return await _reload_thread(session, beat.project_id, beat.thread_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.delete(
    "/plot-beats/{beat_id}",
    response_model=PlotThreadResponse,
    summary="去掉章节上的节拍",
)
async def delete_plot_beat(
    beat_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlotThreadResponse:
    try:
        from app.storage.repos import plot_beat_repo

        beat = await plot_beat_repo.get_by_id(session, beat_id)
        if beat is None:
            raise NotFoundError(f"节拍不存在: {beat_id}")
        project_id = beat.project_id
        thread_id = beat.thread_id
        await plot_thread_service.delete_beat(session, beat_id)
        await background_service.commit_and_notify(session)
        return await _reload_thread(session, project_id, thread_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


async def _reload_thread(
    session: AsyncSession,
    project_id: str,
    thread_id: str,
) -> PlotThreadResponse:
    board = await plot_thread_service.get_board(session, project_id)
    item = next(
        (entry for entry in board.threads if entry.thread.id == thread_id), None
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="情节线不存在"
        )
    return _thread_response(item, board.beats)

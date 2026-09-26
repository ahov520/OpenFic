# -*- coding: utf-8 -*-
"""
Chapters Router - 章节 CRUD API。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.chapter import (
    ChapterCreate,
    ChapterListItem,
    ChapterMerge,
    ChapterMoveToVolume,
    ChapterReorder,
    ChapterResponse,
    ChapterSplit,
    ChapterSplitResponse,
    PreviousChapterEndingResponse,
    ChapterSearchMatch,
    ChapterSearchResponse,
    ChapterSearchResult,
    ChapterUpdate,
    VolumeTreeItem,
    VolumeTreeResponse,
)
from app.api.schemas.plan_check import PlanCheckResponse
from app.background.jobs import service as background_service
from app.core.errors import NotFoundError
from app.storage.chapter_ending import load_previous_chapter_ending
from app.storage.database import get_session
from app.storage.models.chapter import Chapter
from app.storage.plan_coverage import PresentedCheck
from app.storage.repos import margin_note_repo
from app.storage.services import chapter_service, plan_check_service

router = APIRouter(tags=["chapters"])


def _chapter_list_item(chapter: Chapter, counts: dict[str, int]) -> ChapterListItem:
    """列表项附上未划掉旁注数。没有的章保持 0，不另查。"""
    item = ChapterListItem.model_validate(chapter)
    count = counts.get(chapter.id, 0)
    if count == 0:
        return item
    return item.model_copy(update={"open_margin_note_count": count})


def _plan_check_response(
    chapter_id: str, presented: PresentedCheck
) -> PlanCheckResponse:
    return PlanCheckResponse.model_validate(
        {
            "chapter_id": chapter_id,
            "has_plan": presented.has_plan,
            "freshness": presented.freshness,
            "source": presented.source,
            "outcome": presented.outcome,
            "gaps": [
                {
                    "ref": gap.ref,
                    "origin": gap.origin,
                    "plan_text": gap.plan_text,
                    "basis": gap.basis,
                    "missing": list(gap.missing),
                    "detail": gap.detail,
                    "beat_kind": gap.beat_kind,
                    "thread_name": gap.thread_name,
                    "thread_id": gap.thread_id,
                    "change": gap.change,
                }
                for gap in presented.gaps
            ],
            "unchecked": [
                {
                    "ref": line.ref,
                    "origin": line.origin,
                    "plan_text": line.plan_text,
                    "beat_kind": line.beat_kind,
                    "thread_name": line.thread_name,
                }
                for line in presented.unchecked
            ],
            "checked_at": presented.checked_at,
        }
    )


@router.post(
    "/projects/{project_id}/chapters",
    response_model=ChapterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建章节",
)
async def create_chapter(
    project_id: str,
    data: ChapterCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChapterResponse:
    """
    在指定项目下创建新章节。

    Args:
        project_id: 项目 ID。
        data: 章节创建数据。
        session: 数据库 session。

    Returns:
        创建的章节。
    """
    try:
        logger.info(f"创建章节: project_id={project_id}, title={data.title}")
        chapter = await chapter_service.create_chapter(
            session,
            project_id=project_id,
            volume_id=data.volume_id,
            title=data.title,
            content=data.content,
            word_count=data.word_count,
            synopsis=data.synopsis,
            writing_status=data.writing_status,
            word_count_target=data.word_count_target,
        )
        await background_service.commit_and_notify(session)
        return ChapterResponse.model_validate(chapter)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/projects/{project_id}/chapters",
    response_model=VolumeTreeResponse,
    summary="获取章节列表",
)
async def list_chapters(
    project_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VolumeTreeResponse:
    """
    获取指定项目下的所有章节列表（精简版，不含正文）。

    Args:
        project_id: 项目 ID。
        session: 数据库 session。

    Returns:
        章节列表（精简版）。
    """
    try:
        result = await chapter_service.list_chapters(session, project_id)
        return VolumeTreeResponse(
            volumes=[
                VolumeTreeItem(
                    **group.volume.model_dump(),
                    chapters=[
                        _chapter_list_item(chapter, result.open_margin_note_counts)
                        for chapter in group.chapters
                    ],
                )
                for group in result.volumes
            ],
            total_chapters=result.total_chapters,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/chapters/{chapter_id}",
    response_model=ChapterResponse,
    summary="获取章节详情",
)
async def get_chapter(
    chapter_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChapterResponse:
    """
    获取单个章节的详细信息。

    Args:
        chapter_id: 章节 ID。
        session: 数据库 session。

    Returns:
        章节详情。

    Raises:
        HTTPException: 章节不存在时返回 404。
    """
    try:
        chapter = await chapter_service.get_chapter(session, chapter_id)
        return ChapterResponse.model_validate(chapter)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/chapters/{chapter_id}/previous-ending",
    response_model=PreviousChapterEndingResponse | None,
    summary="上一章结尾",
)
async def get_previous_chapter_ending(
    chapter_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PreviousChapterEndingResponse | None:
    """按阅读顺序返回紧邻上一章的结尾摘录。没有则返回 null，不改当前章。"""
    try:
        ending = await load_previous_chapter_ending(session, chapter_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if ending is None:
        return None
    return PreviousChapterEndingResponse(
        chapter_id=ending.chapter_id,
        title=ending.title,
        excerpt=ending.excerpt,
    )


@router.patch(
    "/chapters/{chapter_id}",
    response_model=ChapterResponse,
    summary="更新章节",
)
async def update_chapter(
    chapter_id: str,
    data: ChapterUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChapterResponse:
    """
    更新章节信息。

    Args:
        chapter_id: 章节 ID。
        data: 更新数据。
        session: 数据库 session。

    Returns:
        更新后的章节。

    Raises:
        HTTPException: 章节不存在时返回 404。
    """
    try:
        logger.info(f"更新章节: {chapter_id}")
        chapter = await chapter_service.update_chapter(
            session,
            chapter_id,
            title=data.title,
            content=data.content,
            word_count=data.word_count,
            synopsis=data.synopsis,
            writing_status=data.writing_status,
            word_count_target=(
                data.word_count_target
                if "word_count_target" in data.model_fields_set
                else chapter_service.UNSET
            ),
        )
        await background_service.commit_and_notify(session)
        return ChapterResponse.model_validate(chapter)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/chapters/{chapter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除章节",
)
async def delete_chapter(
    chapter_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """
    删除章节。

    Args:
        chapter_id: 章节 ID。
        session: 数据库 session。

    Raises:
        HTTPException: 章节不存在时返回 404。
    """
    try:
        logger.info(f"删除章节: {chapter_id}")
        await chapter_service.delete_chapter(session, chapter_id)
        await background_service.commit_and_notify(session)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/chapters/reorder",
    response_model=list[ChapterListItem],
    summary="批量重排章节顺序",
)
async def reorder_chapters(
    data: ChapterReorder,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ChapterListItem]:
    """
    批量重排卷内章节顺序。

    Args:
        data: 重排数据（卷 ID + 按新顺序排列的章节 ID 列表）。
        session: 数据库 session。

    Returns:
        更新后的章节列表。

    Raises:
        HTTPException: 章节不存在或不属于指定卷时返回 400。
    """
    try:
        chapters = await chapter_service.reorder_chapters(
            session, data.volume_id, data.chapter_ids
        )
        counts = await margin_note_repo.count_open_by_chapter_ids(
            session, [chapter.id for chapter in chapters]
        )
        await background_service.commit_and_notify(session)
        return [_chapter_list_item(chapter, counts) for chapter in chapters]
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/projects/{project_id}/chapters/search",
    response_model=ChapterSearchResponse,
    summary="搜索章节内容",
)
async def search_chapters(
    project_id: str,
    q: Annotated[str, Query(description="搜索关键词")],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChapterSearchResponse:
    """按内容搜索章节，返回匹配的章节及匹配行。"""
    try:
        result = await chapter_service.search_chapters(session, project_id, q)
        return ChapterSearchResponse(
            results=[
                ChapterSearchResult(
                    chapter_id=r.chapter_id,
                    chapter_title=r.chapter_title,
                    volume_title=r.volume_title,
                    matches=[
                        ChapterSearchMatch(
                            line_number=m.line_number, line_text=m.line_text
                        )
                        for m in r.matches
                    ],
                )
                for r in result.results
            ],
            total_chapters=result.total_chapters,
            total_matches=result.total_matches,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/chapters/{chapter_id}/plan-check",
    response_model=PlanCheckResponse,
    summary="读取对照计划检查",
)
async def get_plan_check(
    chapter_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlanCheckResponse:
    """读取留在这一章上的对照结果。计划或正文变了会标成过期。"""
    try:
        presented = await plan_check_service.get_plan_check(session, chapter_id)
        return _plan_check_response(chapter_id, presented)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/chapters/{chapter_id}/plan-check",
    response_model=PlanCheckResponse,
    summary="对照梗概和本章节拍检查正文",
)
async def run_plan_check(
    chapter_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlanCheckResponse:
    """指出梗概或本章节拍里写了、正文里还没有依据的事。"""
    try:
        presented = await plan_check_service.run_plan_check(session, chapter_id)
        return _plan_check_response(chapter_id, presented)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/chapters/{chapter_id}/move-to-volume",
    response_model=ChapterResponse,
    summary="移动章节到卷",
)
async def move_chapter_to_volume(
    chapter_id: str,
    data: ChapterMoveToVolume,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChapterResponse:
    """跨卷移动章节，追加到目标卷末尾。"""
    try:
        logger.info(f"移动章节到卷: {chapter_id} -> volume={data.volume_id}")
        chapter = await chapter_service.move_chapter_to_volume(
            session,
            chapter_id=chapter_id,
            volume_id=data.volume_id,
        )
        await background_service.commit_and_notify(session)
        return ChapterResponse.model_validate(chapter)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/chapters/merge",
    response_model=ChapterResponse,
    summary="合并章节",
)
async def merge_chapters(
    data: ChapterMerge,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChapterResponse:
    """把同一卷里的多章按阅读顺序合并成一章，第一章为目标章，其余章删除。"""
    try:
        logger.info(f"合并章节: {data.chapter_ids}")
        chapter = await chapter_service.merge_chapters(
            session,
            data.chapter_ids,
            title=data.title,
            separator=data.separator,
        )
        await background_service.commit_and_notify(session)
        return ChapterResponse.model_validate(chapter)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/chapters/{chapter_id}/split",
    response_model=ChapterSplitResponse,
    summary="拆分章节",
)
async def split_chapter(
    chapter_id: str,
    data: ChapterSplit,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChapterSplitResponse:
    """从指定行把一章拆成两章，该行起划入紧跟其后的新章。"""
    try:
        logger.info(f"拆分章节: {chapter_id} @ 行 {data.split_line}")
        target, new = await chapter_service.split_chapter(
            session,
            chapter_id,
            data.split_line,
            title=data.title,
        )
        await background_service.commit_and_notify(session)
        return ChapterSplitResponse(
            target=ChapterResponse.model_validate(target),
            new=ChapterResponse.model_validate(new),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# -*- coding: utf-8 -*-
"""
Chapter Revisions Router - 章节历史版本（时间线 / 预览 / 恢复）API。

时间线基于 commit_repo.list_by_chapter 既有查询，联 Revision 补类型与说明；
恢复把所选 commit 记录的历史版本（snapshot_*）写回章节正文与字数，
并旁路节流生成一条 manual Revision（snapshot_*=恢复前内容，可再找回）。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.chapter import ChapterResponse
from app.api.schemas.chapter_revision import (
    ChapterRevisionDetailResponse,
    ChapterRevisionListResponse,
    ChapterRevisionItem,
    ChapterRevisionRestoreResponse,
)
from app.core.errors import NotFoundError
from app.storage.database import get_session
from app.storage.models.commit import Commit
from app.storage.models.revision import Revision
from app.storage.repos import commit_repo, revision_repo
from app.storage.services import chapter_service, manual_revision_service

router = APIRouter(tags=["chapters"])


def _revision_item(commit: Commit, revision: Revision) -> ChapterRevisionItem:
    has_snapshot = commit.snapshot_content is not None or commit.snapshot_content_blob_id is not None
    return ChapterRevisionItem(
        commit_id=commit.id,
        revision_id=revision.id,
        revision_type=revision.revision_type,
        message=revision.message,
        operation=commit.operation,
        created_at=commit.created_at,
        title=commit.snapshot_title,
        word_count=commit.snapshot_word_count,
        has_snapshot=has_snapshot,
    )


@router.get(
    "/chapters/{chapter_id}/revisions",
    response_model=ChapterRevisionListResponse,
    summary="列出章节历史版本时间线",
)
async def list_chapter_revisions(
    chapter_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> ChapterRevisionListResponse:
    """Agent 修订与手动修订混合的时间线，按变更时间倒序。"""
    try:
        await chapter_service.get_chapter(session, chapter_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    commits = await commit_repo.list_by_chapter(session, chapter_id, offset=offset, limit=limit)
    items: list[ChapterRevisionItem] = []
    for commit in commits:
        revision = await revision_repo.get_by_id(session, commit.revision_id)
        if revision is None:
            logger.warning(f"时间线跳过缺失版本的 commit: {commit.id}")
            continue
        items.append(_revision_item(commit, revision))
    return ChapterRevisionListResponse(items=items)


@router.get(
    "/chapters/{chapter_id}/revisions/{commit_id}",
    response_model=ChapterRevisionDetailResponse,
    summary="预览章节历史版本全文",
)
async def get_chapter_revision_detail(
    chapter_id: str,
    commit_id: str,
    session: AsyncSession = Depends(get_session),
) -> ChapterRevisionDetailResponse:
    """返回所选版本保留的章节全文（blob 长正文由仓储层透明还原）。"""
    try:
        await chapter_service.get_chapter(session, chapter_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    commit = await commit_repo.get_by_id(session, commit_id)
    if commit is None or commit.chapter_id != chapter_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"章节的历史版本不存在: {commit_id}",
        )
    revision = await revision_repo.get_by_id(session, commit.revision_id)
    if revision is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"版本记录不存在: {commit.revision_id}",
        )
    return ChapterRevisionDetailResponse(
        **_revision_item(commit, revision).model_dump(),
        content=commit.snapshot_content or "",
    )


@router.post(
    "/chapters/{chapter_id}/revisions/{commit_id}/restore",
    response_model=ChapterRevisionRestoreResponse,
    summary="恢复章节到所选历史版本",
)
async def restore_chapter_revision(
    chapter_id: str,
    commit_id: str,
    session: AsyncSession = Depends(get_session),
) -> ChapterRevisionRestoreResponse:
    """把所选版本（snapshot_*）写回章节正文与字数，显式旁路节流。

    恢复本身会生成一条 manual Revision：恢复前的当前内容作为其快照
    记入时间线，被覆盖的状态可再找回。
    """
    logger.info(f"恢复章节历史版本: chapter_id={chapter_id}, commit_id={commit_id}")
    try:
        chapter, revision = await manual_revision_service.restore_chapter_to_commit(
            session,
            chapter_id=chapter_id,
            commit_id=commit_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ChapterRevisionRestoreResponse(
        revision_id=revision.id,
        chapter=ChapterResponse.model_validate(chapter),
    )

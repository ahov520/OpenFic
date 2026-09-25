# -*- coding: utf-8 -*-
"""Manual Revision Service - 手动修订服务。

把用户在编辑器里的保存与历史版本恢复并入 revisions/commits 版本体系，
与 Agent 修订共用同一条时间线。

依赖方向红线：本模块只依赖 storage 层（models/repos/core），
不 import app.agent_runtime。内联/落 blob 的分流与
agent_runtime/revisions.py:_store_content 保持同一口径（同一
INLINE_THRESHOLD 阈值与 revision_content_blob_repo.put 压缩去重），
属约 5 行的薄封装重写，避免形成 storage → agent_runtime 的坏依赖。

节流语义：距该章最近一条 manual 修订（commit）——
- 时间间隔 ≥ MANUAL_REVISION_MIN_INTERVAL_SECONDS（10 分钟），或
- 字数变化 ≥ MANUAL_REVISION_MIN_WORD_DELTA（相对最近一条 manual
  commit 的 new_word_count，累计增长也能触发）
才新建；恢复操作显式旁路节流。
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.editor_content_limits import validate_editor_content
from app.core.errors import NotFoundError
from app.storage.models.chapter import Chapter
from app.storage.models.commit import Commit
from app.storage.models.revision import Revision
from app.storage.repos import (
    chapter_repo,
    commit_repo,
    project_repo,
    revision_content_blob_repo,
    revision_repo,
)
from app.storage.services import version_control_service

# 距该章最近一条 manual 修订的最小时间间隔（秒）
MANUAL_REVISION_MIN_INTERVAL_SECONDS = 600
# 触发记录的最小字数变化
MANUAL_REVISION_MIN_WORD_DELTA = 200
# 节流基准回看的最近 commit 数：覆盖最近这些条仍找不到 manual 修订，
# 说明其间已有大量 Agent 变更，本次保存值得记录。
MANUAL_REVISION_SCAN_LIMIT = 20

MANUAL_SAVE_MESSAGE = "手动保存"
RESTORE_MESSAGE = "恢复历史版本"


async def _store_content(
    session: AsyncSession,
    content: str | None,
) -> tuple[str | None, str | None]:
    """返回 (inline_value, blob_id)。

    达到内联阈值的长文本按内容寻址存入去重压缩 blob 表并以 id 引用；
    短文本保持内联。与 agent_runtime 的同名辅助同口径。
    """
    if content is None or len(content) < revision_content_blob_repo.INLINE_THRESHOLD:
        return content, None
    return None, await revision_content_blob_repo.put(session, content)


def should_create_manual_revision(
    *,
    latest_created_at: datetime | None,
    latest_word_count: int | None,
    current_word_count: int,
    now: datetime,
) -> bool:
    """定值节流判断（纯函数，便于以定值断言）。

    Args:
        latest_created_at: 该章最近一条 manual commit 的创建时间；None 表示还没有。
        latest_word_count: 最近一条 manual commit 记录的字数（new_word_count）。
        current_word_count: 本次保存后的章节字数。
        now: 当前时间（由调用方传入，保证可测）。

    Returns:
        距最近一条 manual 修订 ≥10 分钟或字数变化 ≥200 时为 True。
    """
    if latest_created_at is None or latest_word_count is None:
        return True
    if abs(current_word_count - latest_word_count) >= MANUAL_REVISION_MIN_WORD_DELTA:
        return True
    # SQLite 读回的 datetime 可能丢失时区信息，统一按 UTC 解释
    if latest_created_at.tzinfo is None:
        latest_created_at = latest_created_at.replace(tzinfo=UTC)
    elapsed_seconds = (now - latest_created_at).total_seconds()
    return elapsed_seconds >= MANUAL_REVISION_MIN_INTERVAL_SECONDS


async def create_manual_revision(
    session: AsyncSession,
    *,
    chapter: Chapter,
    old_title: str | None,
    old_content: str | None,
    old_word_count: int | None,
    new_content: str | None,
    new_word_count: int,
    message: str = MANUAL_SAVE_MESSAGE,
) -> Revision:
    """创建一条 manual Revision + Commit（不走节流，调用方自行判断是否需要）。

    snapshot_* 记录变更前状态，new_* 记录变更后状态；
    长正文走 revision_content_blob_repo.put 的压缩去重 blob。
    """
    project = await project_repo.get_by_id(session, chapter.project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {chapter.project_id}")

    now = datetime.now(UTC)
    revision = await revision_repo.create(
        session,
        Revision(
            project_id=chapter.project_id,
            message=message,
            revision_type="manual",
            status="completed",
            started_at=now,
            finished_at=now,
            project_snapshot_title=project.title,
            project_snapshot_description=project.description,
            project_snapshot_word_count=project.word_count,
            project_snapshot_chapter_count=project.chapter_count,
        ),
    )

    snapshot_content, snapshot_content_blob_id = await _store_content(session, old_content)
    stored_new_content, new_content_blob_id = await _store_content(session, new_content)
    await commit_repo.create(
        session,
        Commit(
            revision_id=revision.id,
            chapter_id=chapter.id,
            operation="update",
            snapshot_title=old_title,
            snapshot_content=snapshot_content,
            snapshot_content_blob_id=snapshot_content_blob_id,
            snapshot_word_count=old_word_count,
            snapshot_order=chapter.order,
            new_title=chapter.title,
            new_content=stored_new_content,
            new_content_blob_id=new_content_blob_id,
            new_word_count=new_word_count,
            new_order=chapter.order,
        ),
    )
    return revision


async def latest_manual_change_for_chapter(
    session: AsyncSession,
    chapter_id: str,
) -> tuple[Commit, Revision] | None:
    """该章最近一条手动修订的 (Commit, Revision)。

    Revision 是项目级的（没有 chapter_id），章节归属记录在 Commit 上；
    这里复用 commit_repo.list_by_chapter 既有查询（按时间倒序、含 blob 还原），
    逐条用主键取所属 Revision 判型，遇到第一条 manual 即返回。
    用户保存间隔里通常最近一条就是 manual（每次 manual 后节流重新起算），
    因此常态只做一两次主键查询。
    """
    commits = await commit_repo.list_by_chapter(
        session,
        chapter_id,
        limit=MANUAL_REVISION_SCAN_LIMIT,
    )
    for commit in commits:
        revision = await revision_repo.get_by_id(session, commit.revision_id)
        if revision is not None and revision.revision_type == "manual":
            return commit, revision
    return None


async def maybe_create_manual_revision(
    session: AsyncSession,
    *,
    chapter: Chapter,
    old_title: str | None,
    old_content: str | None,
    old_word_count: int | None,
) -> Revision | None:
    """保存热路径入口：按定值节流判断是否记录本次内容变化。

    节流未命中返回 None（不新建 Revision）；命中则新建 manual Revision + Commit。
    时间基准取该章最近一条 manual Revision 的 created_at，字数基准取其
    Commit 的 new_word_count（相对它的累计变化达到阈值也会触发）。
    """
    latest_change = await latest_manual_change_for_chapter(session, chapter.id)
    latest_commit, latest_revision = latest_change if latest_change else (None, None)
    if not should_create_manual_revision(
        latest_created_at=latest_revision.created_at if latest_revision else None,
        latest_word_count=latest_commit.new_word_count if latest_commit else None,
        current_word_count=chapter.word_count,
        now=datetime.now(UTC),
    ):
        return None
    return await create_manual_revision(
        session,
        chapter=chapter,
        old_title=old_title,
        old_content=old_content,
        old_word_count=old_word_count,
        new_content=chapter.content,
        new_word_count=chapter.word_count,
        message=MANUAL_SAVE_MESSAGE,
    )


async def restore_chapter_to_commit(
    session: AsyncSession,
    *,
    chapter_id: str,
    commit_id: str,
) -> tuple[Chapter, Revision]:
    """把章节正文恢复到所选 commit 记录的历史版本（snapshot_*），旁路节流。

    恢复在事务内先读当前内容并作为新 manual revision 的 snapshot_* 记入
    时间线——任何被覆盖的状态都可再找回；随后写回章节正文与字数。
    """
    chapter = await chapter_repo.get_by_id(session, chapter_id)
    if chapter is None:
        raise NotFoundError(f"章节不存在: {chapter_id}")
    commit = await commit_repo.get_by_id(session, commit_id)
    if commit is None or commit.chapter_id != chapter_id:
        raise NotFoundError(f"章节的历史版本不存在: {commit_id}")
    if commit.snapshot_content is None and commit.snapshot_content_blob_id is None:
        raise ValueError("该版本没有可恢复的历史快照")

    restored_content = commit.snapshot_content or ""
    # 与 update_chapter 保存路径同一道内容上限校验（快照内容也可能超限）
    validate_editor_content(restored_content)
    if commit.snapshot_word_count is not None:
        restored_word_count = commit.snapshot_word_count
    else:
        # 与 update_chapter 保存路径同一计数口径（懒加载避免模块环）
        from app.storage.services.chapter_service import _count_words

        restored_word_count = _count_words(restored_content)

    # 显式旁路节流：恢复本身就是要留下一条可追溯的版本记录
    revision = await create_manual_revision(
        session,
        chapter=chapter,
        old_title=chapter.title,
        old_content=chapter.content,
        old_word_count=chapter.word_count,
        new_content=restored_content,
        new_word_count=restored_word_count,
        message=RESTORE_MESSAGE,
    )

    chapter.content = restored_content
    chapter.word_count = restored_word_count
    chapter.updated_at = datetime.now(UTC)
    chapter = await chapter_repo.update_chapter(session, chapter)
    await version_control_service.refresh_project_stats(session, chapter.project_id)

    # 检索索引维护与普通保存同口径：正文已变化，标脏并按需触发自动索引
    from app.retrieval.chapter_index import (
        ChapterIndexIntegrationService,
        safe_maybe_enqueue_auto_index,
    )
    from app.retrieval.index_status import schedule_emit_index_status

    await ChapterIndexIntegrationService().mark_chapter_stale_if_changed(session, chapter)
    await safe_maybe_enqueue_auto_index(session, project_id=chapter.project_id)
    schedule_emit_index_status(session, chapter.project_id)
    return chapter, revision

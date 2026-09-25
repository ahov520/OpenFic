# -*- coding: utf-8 -*-
"""manual_revision_service 服务层测试。

节流判断以定值断言（10 分钟 / 200 字），不经真实等待；
恢复专项（旁路节流、恢复后内容等于所选 snapshot_*）见
tests/api/test_chapter_revisions.py 的端到端覆盖。
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models.chapter import Chapter
from app.storage.models.commit import Commit
from app.storage.models.project import Project
from app.storage.models.revision import Revision
from app.storage.models.volume import Volume
from app.storage.repos import commit_repo, revision_repo
from app.storage.services import chapter_service, manual_revision_service
from app.storage.services.manual_revision_service import (
    MANUAL_REVISION_MIN_INTERVAL_SECONDS,
    MANUAL_REVISION_MIN_WORD_DELTA,
    should_create_manual_revision,
)

NOW = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# 纯函数：定值节流判断
# ---------------------------------------------------------------------------


def test_throttle_without_any_manual_revision_creates() -> None:
    """该章还没有 manual 修订时，首次保存直接记录。"""
    assert (
        should_create_manual_revision(
            latest_created_at=None,
            latest_word_count=None,
            current_word_count=5,
            now=NOW,
        )
        is True
    )


def test_throttle_all_conditions_unmet_skips_creation() -> None:
    """均不满足：距上次 300 秒（<600）且字数变化 199（<200）→ 不新建。"""
    assert (
        should_create_manual_revision(
            latest_created_at=NOW - timedelta(seconds=300),
            latest_word_count=1000,
            current_word_count=1199,
            now=NOW,
        )
        is False
    )


def test_throttle_time_exceeded_creates() -> None:
    """时间超限：距上次恰好 600 秒，字数只变化 1 → 新建。"""
    assert (
        should_create_manual_revision(
            latest_created_at=NOW - timedelta(seconds=MANUAL_REVISION_MIN_INTERVAL_SECONDS),
            latest_word_count=1000,
            current_word_count=1001,
            now=NOW,
        )
        is True
    )


def test_throttle_word_delta_exceeded_creates() -> None:
    """字数超限：距上次仅 60 秒，但字数变化恰好 200 → 新建。"""
    assert (
        should_create_manual_revision(
            latest_created_at=NOW - timedelta(seconds=60),
            latest_word_count=1000,
            current_word_count=1000 + MANUAL_REVISION_MIN_WORD_DELTA,
            now=NOW,
        )
        is True
    )


# ---------------------------------------------------------------------------
# 服务层：保存热路径钩子（chapter_service.update_chapter）
# ---------------------------------------------------------------------------


async def _create_chapter(session: AsyncSession, *, title: str = "第一章") -> Chapter:
    project = Project(title="测试项目", description="")
    session.add(project)
    await session.flush()
    volume = Volume(project_id=project.id, title="第一卷", order=1, chapter_count=1)
    session.add(volume)
    await session.flush()
    chapter = Chapter(
        project_id=project.id,
        volume_id=volume.id,
        title=title,
        order=1,
        word_count=0,
    )
    session.add(chapter)
    await session.flush()
    return chapter


async def _seed_manual_change(
    session: AsyncSession,
    chapter: Chapter,
    *,
    created_at: datetime,
    new_word_count: int,
    new_content: str = "历史内容",
) -> None:
    """直接种一条指定时间的 manual Revision+Commit，作为节流基准。"""
    revision = await revision_repo.create(
        session,
        Revision(
            project_id=chapter.project_id,
            message=manual_revision_service.MANUAL_SAVE_MESSAGE,
            revision_type="manual",
            status="completed",
            started_at=created_at,
            finished_at=created_at,
            created_at=created_at,
            updated_at=created_at,
            project_snapshot_title="测试项目",
            project_snapshot_description="",
            project_snapshot_word_count=new_word_count,
            project_snapshot_chapter_count=1,
        ),
    )
    await commit_repo.create(
        session,
        Commit(
            revision_id=revision.id,
            chapter_id=chapter.id,
            operation="update",
            snapshot_title=chapter.title,
            snapshot_content="",
            snapshot_word_count=0,
            snapshot_order=chapter.order,
            new_title=chapter.title,
            new_content=new_content,
            new_word_count=new_word_count,
            new_order=chapter.order,
            created_at=created_at,
        ),
    )


async def _count_manual_revisions(session: AsyncSession, chapter: Chapter) -> int:
    commits = await commit_repo.list_by_chapter(session, chapter.id, limit=100)
    count = 0
    for commit in commits:
        revision = await revision_repo.get_by_id(session, commit.revision_id)
        if revision is not None and revision.revision_type == "manual":
            count += 1
    return count


@pytest.mark.asyncio
async def test_first_content_change_creates_manual_revision(session: AsyncSession) -> None:
    """首次内容变化：该章没有 manual 基准 → 新建一条 manual Revision+Commit。"""
    chapter = await _create_chapter(session)

    await chapter_service.update_chapter(
        session, chapter.id, content="第一次保存的正文", word_count=120
    )

    assert await _count_manual_revisions(session, chapter) == 1
    latest_change = await manual_revision_service.latest_manual_change_for_chapter(
        session, chapter.id
    )
    assert latest_change is not None
    commit, revision = latest_change
    assert revision.revision_type == "manual"
    assert commit.new_word_count == 120
    assert commit.new_content == "第一次保存的正文"
    assert commit.snapshot_content == ""
    # 长正文走 blob 压缩去重，短文本保持内联
    assert commit.new_content_blob_id is None


@pytest.mark.asyncio
async def test_throttle_skips_saves_that_meet_no_condition(session: AsyncSession) -> None:
    """均不满足：刚记录过 manual，紧接着的小幅保存不新建（不放大 Revision 数）。"""
    chapter = await _create_chapter(session)

    await chapter_service.update_chapter(
        session, chapter.id, content="第一版正文", word_count=1000
    )
    assert await _count_manual_revisions(session, chapter) == 1

    # 立即再保存：距上次 manual 几秒（<600s），字数变化 5（<200）
    await chapter_service.update_chapter(
        session, chapter.id, content="第一版正文改了一下", word_count=1005
    )
    assert await _count_manual_revisions(session, chapter) == 1


@pytest.mark.asyncio
async def test_throttle_creates_when_time_exceeded(session: AsyncSession) -> None:
    """时间超限：距最近一条 manual 修订 ≥10 分钟的小幅保存也新建。"""
    chapter = await _create_chapter(session)
    await _seed_manual_change(
        session,
        chapter,
        created_at=datetime.now(UTC) - timedelta(seconds=MANUAL_REVISION_MIN_INTERVAL_SECONDS + 60),
        new_word_count=1000,
        new_content="十分钟前的内容",
    )

    await chapter_service.update_chapter(
        session, chapter.id, content="十分钟后的小幅修改", word_count=1002
    )

    assert await _count_manual_revisions(session, chapter) == 2
    latest_change = await manual_revision_service.latest_manual_change_for_chapter(
        session, chapter.id
    )
    assert latest_change is not None
    commit, _ = latest_change
    assert commit.new_content == "十分钟后的小幅修改"


@pytest.mark.asyncio
async def test_throttle_creates_when_word_delta_exceeded(session: AsyncSession) -> None:
    """字数超限：距上次 manual 仅 1 分钟，但相对其快照字数变化 ≥200 → 新建。"""
    chapter = await _create_chapter(session)
    await _seed_manual_change(
        session,
        chapter,
        created_at=datetime.now(UTC) - timedelta(seconds=60),
        new_word_count=1000,
        new_content="一分钟前的内容",
    )

    await chapter_service.update_chapter(
        session, chapter.id, content="大幅扩写的正文内容", word_count=1200
    )

    assert await _count_manual_revisions(session, chapter) == 2


@pytest.mark.asyncio
async def test_word_delta_accumulates_against_latest_manual_snapshot(
    session: AsyncSession,
) -> None:
    """字数基准是最近一条 manual 快照：单次保存变化小，累计达到 200 也触发。"""
    chapter = await _create_chapter(session)
    await _seed_manual_change(
        session,
        chapter,
        created_at=datetime.now(UTC) - timedelta(seconds=60),
        new_word_count=1000,
        new_content="一分钟前的内容",
    )

    # 第一次保存 +50：相对快照 1000 只差 50，不触发
    await chapter_service.update_chapter(
        session, chapter.id, content="小幅增补", word_count=1050
    )
    assert await _count_manual_revisions(session, chapter) == 1

    # 第二次保存累计到 +200：相对最近一条 manual 快照达标，触发
    await chapter_service.update_chapter(
        session, chapter.id, content="继续扩写到达标", word_count=1200
    )
    assert await _count_manual_revisions(session, chapter) == 2


@pytest.mark.asyncio
async def test_hook_failure_does_not_block_save(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """钩子失败只记日志，不阻断保存主路径。"""

    async def _explode(*args, **kwargs):
        raise RuntimeError("节流钩子炸了")

    monkeypatch.setattr(
        manual_revision_service, "maybe_create_manual_revision", _explode
    )
    chapter = await _create_chapter(session)

    updated = await chapter_service.update_chapter(
        session, chapter.id, content="保存不能被钩子拖垮", word_count=99
    )

    assert updated.content == "保存不能被钩子拖垮"
    assert updated.word_count == 99
    assert await _count_manual_revisions(session, chapter) == 0

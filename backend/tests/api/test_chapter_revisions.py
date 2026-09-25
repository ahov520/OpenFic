# -*- coding: utf-8 -*-
"""章节历史版本 API 测试：时间线列表 / 全文预览 / 一键恢复。"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models.chapter import Chapter
from app.storage.models.commit import Commit
from app.storage.models.revision import Revision
from app.storage.repos import chapter_repo, commit_repo, revision_repo


async def _create_project(client: AsyncClient) -> tuple[str, str]:
    response = await client.post("/api/v1/projects", data={"title": "测试小说"})
    assert response.status_code == 201
    project_id = response.json()["id"]
    volumes = (await client.get(f"/api/v1/projects/{project_id}/volumes")).json()
    return project_id, volumes[0]["id"]


async def _create_chapter(client: AsyncClient, project_id: str, volume_id: str) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={"volume_id": volume_id, "title": "第一章", "content": ""},
    )
    assert response.status_code == 201
    return response.json()


async def _patch_chapter(
    client: AsyncClient, chapter_id: str, *, content: str, word_count: int
) -> dict:
    response = await client.patch(
        f"/api/v1/chapters/{chapter_id}",
        json={"content": content, "word_count": word_count},
    )
    assert response.status_code == 200
    return response.json()


async def _get_chapter_model(session: AsyncSession, chapter_id: str) -> Chapter:
    chapter = await chapter_repo.get_by_id(session, chapter_id)
    assert chapter is not None
    return chapter


async def _list_manual_commits(client: AsyncClient, chapter_id: str) -> list[dict]:
    response = await client.get(f"/api/v1/chapters/{chapter_id}/revisions")
    assert response.status_code == 200
    return [item for item in response.json()["items"] if item["revision_type"] == "manual"]


async def _seed_change(
    session: AsyncSession,
    chapter: Chapter,
    *,
    created_at: datetime,
    new_word_count: int,
    new_content: str,
    revision_type: str = "manual",
    message: str | None = None,
    snapshot_word_count: int = 0,
) -> None:
    """种一条指定时间的 Revision+Commit 作为节流基准或时间线样本。"""
    revision = await revision_repo.create(
        session,
        Revision(
            project_id=chapter.project_id,
            message=message or "手动保存",
            revision_type=revision_type,
            status="completed",
            started_at=created_at,
            finished_at=created_at,
            created_at=created_at,
            updated_at=created_at,
            project_snapshot_title="测试小说",
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
            snapshot_word_count=snapshot_word_count,
            snapshot_order=chapter.order,
            new_title=chapter.title,
            new_content=new_content,
            new_word_count=new_word_count,
            new_order=chapter.order,
            created_at=created_at,
        ),
    )


@pytest.mark.asyncio
async def test_timeline_lists_manual_revisions_after_saves(
    client: AsyncClient, session: AsyncSession
) -> None:
    """保存钩子产生的 manual 修订进入时间线，含类型/说明/字数，按时间倒序。"""
    project_id, volume_id = await _create_project(client)
    chapter = await _create_chapter(client, project_id, volume_id)

    # 种一条 1 分钟前的 manual 基准（窗口内），逼后续保存走字数变化通道
    await _seed_change(
        session,
        await _get_chapter_model(session, chapter["id"]),
        created_at=datetime.now(UTC) - timedelta(seconds=60),
        new_word_count=100,
        new_content="一分钟前的内容",
    )

    # 保存一：相对基准字数变化 250（≥200）→ 新建 manual 修订
    await _patch_chapter(client, chapter["id"], content="第一版正文", word_count=350)
    # 保存二：相对最近一条 manual 快照（350）变化 210（≥200）→ 再新建
    await _patch_chapter(client, chapter["id"], content="第二版正文", word_count=560)
    # 种一条 30 秒前的 agent 修订，验证时间线混合呈现两种类型
    await _seed_change(
        session,
        await _get_chapter_model(session, chapter["id"]),
        created_at=datetime.now(UTC) - timedelta(seconds=30),
        new_word_count=590,
        new_content="Agent 改写后的内容",
        revision_type="agent",
        message="按细纲推进第二节",
        snapshot_word_count=560,
    )

    response = await client.get(f"/api/v1/chapters/{chapter['id']}/revisions")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 4

    # 倒序：最新在前（保存二 → 保存一 → agent → 种子）；word_count 是该版本快照的字数
    assert items[0]["revision_type"] == "manual"
    assert items[0]["message"] == "手动保存"
    assert items[0]["word_count"] == 350  # 保存二记录的快照是保存一的内容
    assert items[0]["has_snapshot"] is True
    assert items[1]["word_count"] == 0  # 保存一的快照是创建时的空章
    assert items[2]["revision_type"] == "agent"
    assert items[2]["message"] == "按细纲推进第二节"
    assert items[2]["word_count"] == 560  # agent 条目的快照是保存二的内容
    assert items[3]["word_count"] == 0  # 种子条目的快照同样是空章
    # 每条都带所属 revision 信息
    assert all(item["revision_id"] for item in items)


@pytest.mark.asyncio
async def test_restore_right_after_save_creates_manual_revision(
    client: AsyncClient, session: AsyncSession
) -> None:
    """刚保存完立即恢复仍生成 manual revision（恢复显式旁路节流）。"""
    project_id, volume_id = await _create_project(client)
    chapter = await _create_chapter(client, project_id, volume_id)
    await _seed_change(
        session,
        await _get_chapter_model(session, chapter["id"]),
        created_at=datetime.now(UTC) - timedelta(seconds=60),
        new_word_count=100,
        new_content="一分钟前的内容",
    )

    # 保存一：字数变化 250 → 新建 manual（snapshot=""，new=第一版正文）
    await _patch_chapter(client, chapter["id"], content="第一版正文", word_count=350)
    # 保存二：相对保存一快照变化 210 → 再新建 manual（snapshot=第一版正文）
    await _patch_chapter(client, chapter["id"], content="第二版正文", word_count=560)
    manual_items = await _list_manual_commits(client, chapter["id"])
    assert len(manual_items) == 3

    # 立即恢复到「保存二」的快照（= 第一版正文），此时距最近 manual 仅数秒
    commit_to_restore = manual_items[0]["commit_id"]
    response = await client.post(
        f"/api/v1/chapters/{chapter['id']}/revisions/{commit_to_restore}/restore"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["revision_id"]

    # 恢复后章节内容等于所选 commit 的 snapshot_*
    assert body["chapter"]["content"] == "第一版正文"
    assert body["chapter"]["word_count"] == 350

    # 恢复旁路节流：窗口内依然生成了一条新的 manual revision
    manual_after = await _list_manual_commits(client, chapter["id"])
    assert len(manual_after) == 4
    newest = manual_after[0]
    assert newest["commit_id"] != commit_to_restore
    assert newest["message"] == "恢复历史版本"


@pytest.mark.asyncio
async def test_restore_overwrites_edits_made_during_restore_window(
    client: AsyncClient, session: AsyncSession
) -> None:
    """恢复期间的并发编辑场景：被覆盖内容先进恢复版的快照，仍可再找回。"""
    project_id, volume_id = await _create_project(client)
    chapter = await _create_chapter(client, project_id, volume_id)
    await _seed_change(
        session,
        await _get_chapter_model(session, chapter["id"]),
        created_at=datetime.now(UTC) - timedelta(seconds=60),
        new_word_count=100,
        new_content="一分钟前的内容",
    )

    # 两次保存都走字数变化通道，各生成一条 manual 修订
    await _patch_chapter(client, chapter["id"], content="第一版正文", word_count=350)
    await _patch_chapter(client, chapter["id"], content="第二版正文", word_count=560)
    items_before = await _list_manual_commits(client, chapter["id"])
    assert len(items_before) == 3
    commit_to_restore = items_before[0]  # 保存二，其快照是「第一版正文」

    # 恢复前章节又被改成别的内容（窗口内小幅修改，不生成修订），随后立即恢复
    await _patch_chapter(client, chapter["id"], content="恢复前又改了一版", word_count=580)
    response = await client.post(
        f"/api/v1/chapters/{chapter['id']}/revisions/{commit_to_restore['commit_id']}/restore"
    )
    assert response.status_code == 200

    # 被覆盖的「恢复前又改了一版」保留在恢复版修订的快照里
    items = (await client.get(f"/api/v1/chapters/{chapter['id']}/revisions")).json()["items"]
    restore_item = items[0]
    assert restore_item["message"] == "恢复历史版本"

    preview = await client.get(
        f"/api/v1/chapters/{chapter['id']}/revisions/{restore_item['commit_id']}"
    )
    assert preview.status_code == 200
    assert preview.json()["content"] == "恢复前又改了一版"
    # 章节本身已回到所选快照（= 第一版正文）
    final = await client.get(f"/api/v1/chapters/{chapter['id']}")
    assert final.json()["content"] == "第一版正文"
    assert final.json()["word_count"] == 350


@pytest.mark.asyncio
async def test_timeline_returns_404_for_unknown_chapter(client: AsyncClient) -> None:
    response = await client.get("/api/v1/chapters/nonexistent/revisions")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_restore_rejects_commit_without_snapshot(
    client: AsyncClient, session: AsyncSession
) -> None:
    """没有历史快照的条目（如 create 操作）恢复返回 400。"""
    project_id, volume_id = await _create_project(client)
    empty_chapter_response = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={"volume_id": volume_id, "title": "空章", "content": ""},
    )
    assert empty_chapter_response.status_code == 201
    empty_chapter = empty_chapter_response.json()

    # 种一条 snapshot 为 None 的 create 型 commit
    revision = await revision_repo.create(
        session,
        Revision(
            project_id=project_id,
            message="创建章节",
            revision_type="manual",
            status="completed",
            project_snapshot_title="测试小说",
            project_snapshot_word_count=0,
            project_snapshot_chapter_count=1,
        ),
    )
    create_commit = await commit_repo.create(
        session,
        Commit(
            revision_id=revision.id,
            chapter_id=empty_chapter["id"],
            operation="create",
            new_title=empty_chapter["title"],
            new_content="",
            new_word_count=0,
            new_order=0,
        ),
    )

    response = await client.post(
        f"/api/v1/chapters/{empty_chapter['id']}/revisions/{create_commit.id}/restore"
    )
    assert response.status_code == 400

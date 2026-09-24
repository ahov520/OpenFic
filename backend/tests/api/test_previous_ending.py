# -*- coding: utf-8 -*-
"""上一章结尾：只读摘录，不进当前章正文、字数或导出。"""

import json

import pytest
from httpx import AsyncClient

from app.background.events.publisher import BackgroundEventPublisher
from app.background.jobs import service as background_service
from app.background.runtime.context import JobContext
from app.background.runtime.dispatcher import dispatch_job
from app.chapter_export import service as chapter_export_service
from app.storage.chapter_ending import (
    PREVIOUS_ENDING_NOTICE,
    PREVIOUS_ENDING_UNIT_LIMIT,
)
from app.storage.services.chapter_service import _count_words


async def _create_project(client: AsyncClient) -> tuple[str, str]:
    response = await client.post("/api/v1/projects", data={"title": "测试小说"})
    assert response.status_code == 201
    project_id = response.json()["id"]
    volumes = (await client.get(f"/api/v1/projects/{project_id}/volumes")).json()
    return project_id, volumes[0]["id"]


async def _create_chapter(
    client: AsyncClient,
    project_id: str,
    volume_id: str,
    *,
    title: str,
    content: str,
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={
            "volume_id": volume_id,
            "title": title,
            "content": content,
            "word_count": _count_words(content),
        },
    )
    assert response.status_code == 201
    return response.json()


def _long_previous(ending: str) -> str:
    return f"开头独有的句子在这里。{'垫' * 200}{ending}"


@pytest.mark.asyncio
async def test_previous_ending_is_the_tail_and_stays_out_of_this_chapter(
    client: AsyncClient,
) -> None:
    project_id, volume_id = await _create_project(client)
    ending = "青鸟停在最后。"
    previous = await _create_chapter(
        client,
        project_id,
        volume_id,
        title="第一章",
        content=_long_previous(ending),
    )
    current_content = "本章只有这一句。"
    current = await _create_chapter(
        client,
        project_id,
        volume_id,
        title="第二章",
        content=current_content,
    )

    first = await client.get(f"/api/v1/chapters/{previous['id']}/previous-ending")
    assert first.status_code == 200
    assert first.json() is None

    shown = await client.get(f"/api/v1/chapters/{current['id']}/previous-ending")
    assert shown.status_code == 200
    payload = shown.json()
    assert payload["chapter_id"] == previous["id"]
    assert payload["title"] == "第一章"
    assert payload["excerpt"].endswith(ending)
    assert "开头独有的句子在这里。" not in payload["excerpt"]
    assert _count_words(payload["excerpt"]) == PREVIOUS_ENDING_UNIT_LIMIT

    again = (await client.get(f"/api/v1/chapters/{current['id']}")).json()
    assert again["content"] == current_content
    assert again["word_count"] == current["word_count"]
    assert ending not in again["content"]

    context = await client.get(
        f"/api/v1/projects/{project_id}/chapter-context/context",
        params={"chapter_id": current["id"]},
    )
    assert context.status_code == 200
    latest = json.loads(context.json()["latest_field"]["content"])
    assert latest["content"] == current_content
    assert latest["word_count"] == current["word_count"]
    assert ending not in latest["content"]
    bridge = latest["previous_chapter_ending"]
    assert bridge["excerpt"] == payload["excerpt"]
    assert bridge["notice"] == PREVIOUS_ENDING_NOTICE
    assert "上一章" in bridge["notice"]
    assert "不是本章正文" in bridge["notice"]

    first_context = await client.get(
        f"/api/v1/projects/{project_id}/chapter-context/context",
        params={"chapter_id": previous["id"]},
    )
    first_latest = json.loads(first_context.json()["latest_field"]["content"])
    assert "previous_chapter_ending" not in first_latest


@pytest.mark.asyncio
async def test_previous_ending_refreshes_after_the_previous_chapter_is_saved(
    client: AsyncClient,
) -> None:
    project_id, volume_id = await _create_project(client)
    previous = await _create_chapter(
        client,
        project_id,
        volume_id,
        title="第一章",
        content=_long_previous("青鸟停在最后。"),
    )
    current = await _create_chapter(
        client,
        project_id,
        volume_id,
        title="第二章",
        content="接着写。",
    )
    revised = _long_previous("新的一句停在灯塔。")
    updated = await client.patch(
        f"/api/v1/chapters/{previous['id']}",
        json={"content": revised, "word_count": _count_words(revised)},
    )
    assert updated.status_code == 200

    shown = await client.get(f"/api/v1/chapters/{current['id']}/previous-ending")
    excerpt = shown.json()["excerpt"]
    assert excerpt.endswith("新的一句停在灯塔。")
    assert "青鸟停在最后。" not in excerpt
    current_after = (await client.get(f"/api/v1/chapters/{current['id']}")).json()
    assert current_after["content"] == "接着写。"
    assert current_after["word_count"] == current["word_count"]


@pytest.mark.asyncio
async def test_empty_previous_chapter_and_cross_volume_order(
    client: AsyncClient,
) -> None:
    project_id, first_volume_id = await _create_project(client)
    second_volume = await client.post(
        f"/api/v1/projects/{project_id}/volumes",
        json={"title": "第二卷"},
    )
    assert second_volume.status_code == 201
    second_volume_id = second_volume.json()["id"]

    ending = "跨卷之前停在渡口。"
    await _create_chapter(
        client,
        project_id,
        first_volume_id,
        title="卷一末",
        content=_long_previous(ending),
    )
    blank = await _create_chapter(
        client,
        project_id,
        first_volume_id,
        title="空章",
        content="   ",
    )
    followed_blank = await _create_chapter(
        client,
        project_id,
        second_volume_id,
        title="卷二首",
        content="第二卷开头。",
    )
    hidden = await client.get(
        f"/api/v1/chapters/{followed_blank['id']}/previous-ending"
    )
    assert hidden.json() is None

    await client.delete(f"/api/v1/chapters/{blank['id']}")
    shown = await client.get(f"/api/v1/chapters/{followed_blank['id']}/previous-ending")
    assert shown.json()["excerpt"].endswith(ending)
    assert "开头独有的句子在这里。" not in shown.json()["excerpt"]


@pytest.mark.asyncio
async def test_missing_chapter_previous_ending_is_not_found(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/chapters/missing-chapter/previous-ending")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_does_not_copy_previous_ending_into_the_next_chapter(
    client: AsyncClient,
    session,
    monkeypatch,
    tmp_path,
) -> None:
    async def skip_cancellation_check(_context: JobContext) -> None:
        return None

    monkeypatch.setattr(
        chapter_export_service.settings, "chapter_exports_dir", tmp_path
    )
    monkeypatch.setattr(JobContext, "check_cancelled", skip_cancellation_check)
    project_id, volume_id = await _create_project(client)
    ending = "青鸟停在最后。"
    await _create_chapter(
        client,
        project_id,
        volume_id,
        title="第一章",
        content=_long_previous(ending),
    )
    current = await _create_chapter(
        client,
        project_id,
        volume_id,
        title="第二章",
        content="本章只有这一句。",
    )

    created = await client.post(
        f"/api/v1/projects/{project_id}/chapter-exports",
        json={
            "selected_volume_ids": [],
            "included_chapter_ids": [current["id"]],
            "excluded_chapter_ids": [],
            "local_date": "2026-09-24",
        },
    )
    assert created.status_code == 201
    job = await background_service.get_job(session, created.json()["id"])
    assert job is not None
    job.status = "running"
    await session.commit()

    context = JobContext(
        session=session, job=job, publisher=BackgroundEventPublisher(None)
    )
    result = await dispatch_job(context)
    await background_service.mark_succeeded(
        session, context.publisher, context.job, result=result
    )
    await session.commit()

    download = await client.get(
        f"/api/v1/projects/{project_id}/chapter-exports/{job.id}/download"
    )
    text = download.content.decode("utf-8-sig")
    assert download.status_code == 200
    assert "本章只有这一句。" in text
    assert ending not in text
    assert result["word_count"] == current["word_count"]

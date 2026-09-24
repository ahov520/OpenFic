# -*- coding: utf-8 -*-
"""旁注 API：刷新还在，划掉仍保留，字数和导出正文都不含旁注。"""

import json

import pytest
from httpx import AsyncClient

from app.background.events.publisher import BackgroundEventPublisher
from app.background.jobs import service as background_service
from app.background.runtime.context import JobContext
from app.background.runtime.dispatcher import dispatch_job
from app.chapter_export import service as chapter_export_service
from app.storage.margin_notes import MARGIN_NOTE_NOTICE
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
    content: str,
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={
            "volume_id": volume_id,
            "title": "夜航",
            "content": content,
            "word_count": _count_words(content),
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_margin_note_survives_reload_and_strike_keeps_the_record(
    client: AsyncClient,
) -> None:
    project_id, volume_id = await _create_project(client)
    content = "走廊很暗。他推开门。灯还亮着。"
    chapter = await _create_chapter(client, project_id, volume_id, content)
    anchor = "他推开门。"
    body = "这句先别删，动机不清楚。"

    created = await client.post(
        f"/api/v1/chapters/{chapter['id']}/margin-notes",
        json={
            "anchor_text": anchor,
            "context_before": "走廊很暗。",
            "context_after": "灯还亮着。",
            "body": body,
        },
    )
    assert created.status_code == 201
    note = created.json()
    assert note["anchor_text"] == anchor
    assert note["body"] == body
    assert note["status"] == "open"
    assert note["alignment"] == "aligned"
    assert content[note["start"] : note["end"]] == anchor

    reloaded = await client.get(f"/api/v1/chapters/{chapter['id']}/margin-notes")
    assert reloaded.status_code == 200
    assert reloaded.json() == [note]

    struck = await client.patch(
        f"/api/v1/chapters/{chapter['id']}/margin-notes/{note['id']}",
        json={"status": "struck"},
    )
    assert struck.status_code == 200
    assert struck.json()["status"] == "struck"
    assert struck.json()["anchor_text"] == anchor
    assert struck.json()["body"] == body

    after_strike = await client.get(f"/api/v1/chapters/{chapter['id']}/margin-notes")
    assert len(after_strike.json()) == 1
    assert after_strike.json()[0]["status"] == "struck"
    assert after_strike.json()[0]["body"] == body


@pytest.mark.asyncio
async def test_margin_note_does_not_change_word_count_or_manuscript(
    client: AsyncClient,
) -> None:
    project_id, volume_id = await _create_project(client)
    content = "他推开门。"
    chapter = await _create_chapter(client, project_id, volume_id, content)
    body = "这句先别删。动机不清楚，后文再决定要不要留。"
    assert _count_words(content + body) > chapter["word_count"]

    created = await client.post(
        f"/api/v1/chapters/{chapter['id']}/margin-notes",
        json={"anchor_text": "他推开门。", "body": body},
    )
    assert created.status_code == 201

    refreshed = await client.get(f"/api/v1/chapters/{chapter['id']}")
    assert refreshed.status_code == 200
    saved = refreshed.json()
    assert saved["content"] == content
    assert body not in saved["content"]
    assert saved["word_count"] == chapter["word_count"]
    assert _count_words(saved["content"]) == chapter["word_count"]


@pytest.mark.asyncio
async def test_empty_selection_is_rejected(client: AsyncClient) -> None:
    project_id, volume_id = await _create_project(client)
    chapter = await _create_chapter(client, project_id, volume_id, "他推开门。")

    for anchor in ("", "   ", "\n"):
        response = await client.post(
            f"/api/v1/chapters/{chapter['id']}/margin-notes",
            json={"anchor_text": anchor, "body": "记一笔"},
        )
        assert response.status_code == 400
        assert "选中" in response.json()["detail"]

    listed = await client.get(f"/api/v1/chapters/{chapter['id']}/margin-notes")
    assert listed.json() == []


@pytest.mark.asyncio
async def test_changed_sentence_is_marked_misaligned_without_a_range(
    client: AsyncClient,
) -> None:
    project_id, volume_id = await _create_project(client)
    chapter = await _create_chapter(
        client, project_id, volume_id, "他推开门。灯还亮着。"
    )
    created = await client.post(
        f"/api/v1/chapters/{chapter['id']}/margin-notes",
        json={"anchor_text": "他推开门。", "body": "先留着。"},
    )
    assert created.status_code == 201

    updated = await client.patch(
        f"/api/v1/chapters/{chapter['id']}",
        json={
            "content": "他关上了门。灯还亮着。",
            "word_count": _count_words("他关上了门。灯还亮着。"),
        },
    )
    assert updated.status_code == 200

    listed = await client.get(f"/api/v1/chapters/{chapter['id']}/margin-notes")
    note = listed.json()[0]
    assert note["alignment"] == "misaligned"
    assert note["anchor_text"] == "他推开门。"
    assert note["start"] is None
    assert note["end"] is None


@pytest.mark.asyncio
async def test_export_manuscript_omits_margin_note(
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
    content = "他推开门。"
    chapter = await _create_chapter(client, project_id, volume_id, content)
    body = "旁注不应出现在导出正文里。"
    created_note = await client.post(
        f"/api/v1/chapters/{chapter['id']}/margin-notes",
        json={"anchor_text": content, "body": body},
    )
    assert created_note.status_code == 201

    created = await client.post(
        f"/api/v1/projects/{project_id}/chapter-exports",
        json={
            "selected_volume_ids": [volume_id],
            "included_chapter_ids": [],
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
    assert "他推开门。" in text
    assert body not in text
    assert result["word_count"] == chapter["word_count"]


@pytest.mark.asyncio
async def test_agent_context_lists_open_notes_outside_the_manuscript(
    client: AsyncClient,
) -> None:
    project_id, volume_id = await _create_project(client)
    content = "他推开门。灯还亮着。"
    chapter = await _create_chapter(client, project_id, volume_id, content)
    open_body = "这句先别删，动机不清楚。"
    struck_body = "这句已经改完，不要再提醒。"
    open_note = await client.post(
        f"/api/v1/chapters/{chapter['id']}/margin-notes",
        json={"anchor_text": "他推开门。", "body": open_body},
    )
    struck = await client.post(
        f"/api/v1/chapters/{chapter['id']}/margin-notes",
        json={"anchor_text": "灯还亮着。", "body": struck_body},
    )
    assert open_note.status_code == 201
    assert struck.status_code == 201
    await client.patch(
        f"/api/v1/chapters/{chapter['id']}/margin-notes/{struck.json()['id']}",
        json={"status": "struck"},
    )

    context = await client.get(
        f"/api/v1/projects/{project_id}/chapter-context/context",
        params={"chapter_id": chapter["id"]},
    )
    assert context.status_code == 200
    latest = json.loads(context.json()["latest_field"]["content"])
    assert latest["content"] == content
    assert open_body not in latest["content"]
    assert struck_body not in latest["content"]
    assert latest["word_count"] == chapter["word_count"]
    section = latest["author_margin_notes"]
    assert section["notice"] == MARGIN_NOTE_NOTICE
    assert "不是正文" in section["notice"]
    assert section["notes"] == [{"anchor": "他推开门。", "note": open_body}]
    assert struck_body not in json.dumps(section, ensure_ascii=False)


async def _note(
    client: AsyncClient,
    chapter_id: str,
    anchor: str,
    body: str,
) -> dict:
    response = await client.post(
        f"/api/v1/chapters/{chapter_id}/margin-notes",
        json={"anchor_text": anchor, "body": body},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_open_margin_notes_follow_reading_order_and_drop_when_struck(
    client: AsyncClient,
) -> None:
    """两章各一条时按阅读顺序；已划掉不出现；划掉或删除后这条从清单消失。"""
    project_id, volume_id = await _create_project(client)
    earlier = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={"volume_id": volume_id, "title": "前章", "content": "他推开门。"},
    )
    later = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={"volume_id": volume_id, "title": "后章", "content": "灯还亮着。"},
    )
    assert earlier.status_code == 201
    assert later.status_code == 201
    second_volume = await client.post(
        f"/api/v1/projects/{project_id}/volumes",
        json={"title": "第二卷"},
    )
    assert second_volume.status_code == 201
    finale = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={
            "volume_id": second_volume.json()["id"],
            "title": "卷末",
            "content": "走廊尽头。",
        },
    )
    assert finale.status_code == 201
    earlier_id = earlier.json()["id"]
    later_id = later.json()["id"]
    finale_id = finale.json()["id"]

    finale_note = await _note(
        client, finale_id, "走廊尽头。", "卷末先记下，但应排在最后"
    )
    later_note = await _note(client, later_id, "灯还亮着。", "后章的问题")
    struck = await _note(client, later_id, "灯还亮着。", "这句已经处理")
    earlier_first = await _note(client, earlier_id, "他推开门。", "前章先记")
    earlier_second = await _note(client, earlier_id, "他推开门。", "前章后记")
    struck_response = await client.patch(
        f"/api/v1/chapters/{later_id}/margin-notes/{struck['id']}",
        json={"status": "struck"},
    )
    assert struck_response.status_code == 200

    listed = await client.get(f"/api/v1/projects/{project_id}/margin-notes")
    assert listed.status_code == 200
    notes = listed.json()
    assert [item["id"] for item in notes] == [
        earlier_first["id"],
        earlier_second["id"],
        later_note["id"],
        finale_note["id"],
    ]
    assert [item["chapter_title"] for item in notes] == ["前章", "前章", "后章", "卷末"]
    assert [item["body"] for item in notes] == [
        "前章先记",
        "前章后记",
        "后章的问题",
        "卷末先记下，但应排在最后",
    ]
    assert notes[0]["anchor_text"] == "他推开门。"
    assert notes[2]["chapter_id"] == later_id
    assert all(item["body"] != "这句已经处理" for item in notes)

    struck_later = await client.patch(
        f"/api/v1/chapters/{later_id}/margin-notes/{later_note['id']}",
        json={"status": "struck"},
    )
    assert struck_later.status_code == 200
    after_strike = await client.get(f"/api/v1/projects/{project_id}/margin-notes")
    assert [item["id"] for item in after_strike.json()] == [
        earlier_first["id"],
        earlier_second["id"],
        finale_note["id"],
    ]

    deleted = await client.delete(
        f"/api/v1/chapters/{earlier_id}/margin-notes/{earlier_first['id']}"
    )
    assert deleted.status_code == 204
    after_delete = await client.get(f"/api/v1/projects/{project_id}/margin-notes")
    assert [item["id"] for item in after_delete.json()] == [
        earlier_second["id"],
        finale_note["id"],
    ]


@pytest.mark.asyncio
async def test_open_margin_notes_on_empty_project_is_an_empty_list(
    client: AsyncClient,
) -> None:
    project_id, _volume_id = await _create_project(client)
    listed = await client.get(f"/api/v1/projects/{project_id}/margin-notes")
    assert listed.status_code == 200
    assert listed.json() == []

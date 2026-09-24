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
    assert note["mark"] == "faint"
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
    assert struck.json()["alignment"] == "aligned"
    assert struck.json()["mark"] == "weak"
    assert struck.json()["mark"] != "faint"
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
    assert "margin-note" not in saved["content"]
    assert created.json()["mark"] == "faint"
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
    assert note["mark"] is None
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
    assert "margin-note-mark" not in text
    assert created_note.json()["mark"] == "faint"
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


@pytest.mark.asyncio
async def test_repin_updates_the_same_note_without_touching_the_manuscript(
    client: AsyncClient,
) -> None:
    project_id, volume_id = await _create_project(client)
    original = "他推开门。灯还亮着。窗外在下雨。"
    chapter = await _create_chapter(client, project_id, volume_id, original)
    body = "动机不清楚。"
    created = await client.post(
        f"/api/v1/chapters/{chapter['id']}/margin-notes",
        json={
            "anchor_text": "他推开门。",
            "context_before": "",
            "context_after": "灯还亮着。",
            "body": body,
        },
    )
    assert created.status_code == 201
    note_id = created.json()["id"]
    assert created.json()["mark"] == "faint"

    rewritten = "门还关着。灯还亮着。窗外在下雨。"
    edited = await client.patch(
        f"/api/v1/chapters/{chapter['id']}",
        json={"content": rewritten, "word_count": _count_words(rewritten)},
    )
    assert edited.status_code == 200
    word_count = edited.json()["word_count"]

    drifted = await client.get(f"/api/v1/chapters/{chapter['id']}/margin-notes")
    assert drifted.json()[0]["alignment"] == "misaligned"
    assert drifted.json()[0]["mark"] is None

    repinned = await client.patch(
        f"/api/v1/chapters/{chapter['id']}/margin-notes/{note_id}",
        json={
            "anchor_text": "灯还亮着。",
            "context_before": "门还关着。",
            "context_after": "窗外在下雨。",
        },
    )
    assert repinned.status_code == 200
    note = repinned.json()
    assert note["id"] == note_id
    assert note["body"] == body
    assert note["status"] == "open"
    assert note["anchor_text"] == "灯还亮着。"
    assert note["context_before"] == "门还关着。"
    assert note["context_after"] == "窗外在下雨。"
    assert note["alignment"] == "aligned"
    assert note["mark"] == "faint"
    assert rewritten[note["start"] : note["end"]] == "灯还亮着。"

    listed = await client.get(f"/api/v1/chapters/{chapter['id']}/margin-notes")
    assert [item["id"] for item in listed.json()] == [note_id]

    saved = (await client.get(f"/api/v1/chapters/{chapter['id']}")).json()
    assert saved["content"] == rewritten
    assert body not in saved["content"]
    assert "margin-note" not in saved["content"]
    assert saved["word_count"] == word_count

    context = await client.get(
        f"/api/v1/projects/{project_id}/chapter-context/context",
        params={"chapter_id": chapter["id"]},
    )
    assert context.status_code == 200
    latest = json.loads(context.json()["latest_field"]["content"])
    assert latest["content"] == rewritten
    assert latest["word_count"] == word_count
    section = latest["author_margin_notes"]
    assert section["notes"] == [{"anchor": "灯还亮着。", "note": body}]
    dumped = json.dumps(section, ensure_ascii=False)
    assert "他推开门" not in dumped
    assert "margin-note" not in dumped
    assert "<" not in section["notes"][0]["anchor"]


@pytest.mark.asyncio
async def test_repin_without_a_selection_keeps_the_old_anchor(
    client: AsyncClient,
) -> None:
    project_id, volume_id = await _create_project(client)
    content = "他推开门。灯还亮着。"
    chapter = await _create_chapter(client, project_id, volume_id, content)
    created = await client.post(
        f"/api/v1/chapters/{chapter['id']}/margin-notes",
        json={"anchor_text": "他推开门。", "body": "先留着。"},
    )
    assert created.status_code == 201
    note_id = created.json()["id"]

    for anchor in ("", "   ", "\n"):
        response = await client.patch(
            f"/api/v1/chapters/{chapter['id']}/margin-notes/{note_id}",
            json={
                "anchor_text": anchor,
                "context_before": "前文",
                "context_after": "后文",
            },
        )
        assert response.status_code == 400
        assert "选中" in response.json()["detail"]

    listed = await client.get(f"/api/v1/chapters/{chapter['id']}/margin-notes")
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == note_id
    assert listed.json()[0]["anchor_text"] == "他推开门。"
    assert listed.json()[0]["alignment"] == "aligned"
    saved = (await client.get(f"/api/v1/chapters/{chapter['id']}")).json()
    assert saved["content"] == content
    assert saved["word_count"] == chapter["word_count"]

# -*- coding: utf-8 -*-
"""对照计划检查会留下结果，并在正文或计划变化后过期。"""

import json

import pytest
from httpx import AsyncClient

from app.storage.services import plan_check_service


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
    title: str,
    content: str = "",
    synopsis: str = "",
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={
            "volume_id": volume_id,
            "title": title,
            "content": content,
            "synopsis": synopsis,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_literal_plan_check_persists_and_goes_stale(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没有模型时用字面缺口，刷新还在；改正文或别章节拍不会假装通过。"""

    async def unavailable(_session):
        return None

    monkeypatch.setattr(plan_check_service, "resolve_plan_check_generate", unavailable)
    project_id, volume_id = await _create_project(client)
    chapter = await _create_chapter(
        client,
        project_id,
        volume_id,
        "夜航",
        content="沈照推开门，屋里很静。",
        synopsis="沈照推开门，发现「铜钥匙」。\n门外是林晚棠。",
    )
    later = await _create_chapter(client, project_id, volume_id, "对上", content="后文")
    thread = await client.post(
        f"/api/v1/projects/{project_id}/plot-threads",
        json={"name": "铜镜", "intent": "灯要在后文对上"},
    )
    assert thread.status_code == 201
    thread_id = thread.json()["id"]
    planted = await client.post(
        f"/api/v1/plot-threads/{thread_id}/beats",
        json={"chapter_id": chapter["id"], "kind": "plant", "note": "灯还亮着"},
    )
    assert planted.status_code == 201
    payoff = await client.post(
        f"/api/v1/plot-threads/{thread_id}/beats",
        json={"chapter_id": later["id"], "kind": "payoff", "note": "镜子里是凶手"},
    )
    assert payoff.status_code == 201

    before = chapter["updated_at"]
    checked = await client.post(f"/api/v1/chapters/{chapter['id']}/plan-check")
    assert checked.status_code == 200
    body = checked.json()
    assert body["source"] == "literal"
    assert body["freshness"] == "current"
    assert body["outcome"] == "gaps"
    assert body["has_plan"] is True
    by_ref = {gap["ref"]: gap for gap in body["gaps"]}
    assert by_ref["synopsis:0"]["plan_text"] == "沈照推开门，发现「铜钥匙」。"
    assert by_ref["synopsis:0"]["missing"] == ["铜钥匙"]
    assert by_ref["synopsis:0"]["basis"] == "literal"
    assert by_ref["synopsis:1"]["missing"] == ["林晚棠"]
    beat_gaps = [gap for gap in body["gaps"] if gap["origin"] == "beat"]
    assert len(beat_gaps) == 1
    assert beat_gaps[0]["thread_name"] == "铜镜"
    assert "灯还亮着" in beat_gaps[0]["missing"]
    assert all("凶手" not in gap["plan_text"] for gap in body["gaps"])
    assert all("凶手" not in "".join(gap["missing"]) for gap in body["gaps"])

    stored_chapter = await client.get(f"/api/v1/chapters/{chapter['id']}")
    assert stored_chapter.json()["updated_at"] == before
    assert stored_chapter.json()["content"] == chapter["content"]

    again = await client.get(f"/api/v1/chapters/{chapter['id']}/plan-check")
    assert again.status_code == 200
    assert again.json()["freshness"] == "current"
    assert [gap["ref"] for gap in again.json()["gaps"]] == [
        gap["ref"] for gap in body["gaps"]
    ]

    rewritten = await client.patch(
        f"/api/v1/chapters/{chapter['id']}",
        json={"content": "沈照推开门，发现铜钥匙。门外是林晚棠。铜镜里灯还亮着。"},
    )
    assert rewritten.status_code == 200
    stale = await client.get(f"/api/v1/chapters/{chapter['id']}/plan-check")
    assert stale.json()["freshness"] == "stale"
    assert stale.json()["outcome"] == "gaps"
    assert stale.json()["gaps"][0]["missing"] == ["铜钥匙"]

    note = await client.patch(
        f"/api/v1/plot-beats/{planted.json()['beats'][0]['id']}",
        json={"note": "换成另一句"},
    )
    assert note.status_code == 200
    stale_note = await client.get(f"/api/v1/chapters/{chapter['id']}/plan-check")
    assert stale_note.json()["freshness"] == "stale"


@pytest.mark.asyncio
async def test_plan_check_without_a_plan_is_not_a_pass(client: AsyncClient) -> None:
    project_id, volume_id = await _create_project(client)
    chapter = await _create_chapter(
        client,
        project_id,
        volume_id,
        "空章",
        content="沈照推开门。",
    )
    checked = await client.post(f"/api/v1/chapters/{chapter['id']}/plan-check")
    assert checked.status_code == 200
    body = checked.json()
    assert body["outcome"] == "no_plan"
    assert body["source"] == "empty"
    assert body["has_plan"] is False
    assert body["gaps"] == []
    assert body["freshness"] == "current"

    refreshed = await client.get(f"/api/v1/chapters/{chapter['id']}/plan-check")
    assert refreshed.json()["outcome"] == "no_plan"
    assert refreshed.json()["gaps"] == []

    planned = await client.patch(
        f"/api/v1/chapters/{chapter['id']}",
        json={"synopsis": "门外是林晚棠。"},
    )
    assert planned.status_code == 200
    stale = await client.get(f"/api/v1/chapters/{chapter['id']}/plan-check")
    assert stale.json()["has_plan"] is True
    assert stale.json()["freshness"] == "stale"
    assert stale.json()["outcome"] == "no_plan"
    assert stale.json()["gaps"] == []


@pytest.mark.asyncio
async def test_model_plan_check_uses_the_existing_client(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    async def generate(messages):
        seen["messages"] = messages
        return json.dumps(
            {
                "gaps": [
                    {
                        "ref": "synopsis:1",
                        "because": "梗概写了林晚棠，正文里没有这个人",
                    }
                ]
            },
            ensure_ascii=False,
        )

    async def resolve(_session):
        return generate

    monkeypatch.setattr(plan_check_service, "resolve_plan_check_generate", resolve)
    project_id, volume_id = await _create_project(client)
    chapter = await _create_chapter(
        client,
        project_id,
        volume_id,
        "夜航",
        content="沈照推开门。",
        synopsis="沈照推开门。\n门外是林晚棠。",
    )
    later = await _create_chapter(client, project_id, volume_id, "对上")
    thread = (
        await client.post(
            f"/api/v1/projects/{project_id}/plot-threads",
            json={"name": "铜镜", "intent": "灯要在后文对上"},
        )
    ).json()
    await client.post(
        f"/api/v1/plot-threads/{thread['id']}/beats",
        json={"chapter_id": later["id"], "kind": "payoff", "note": "镜子里是凶手"},
    )

    checked = await client.post(f"/api/v1/chapters/{chapter['id']}/plan-check")
    assert checked.status_code == 200
    body = checked.json()
    assert body["source"] == "model"
    assert body["outcome"] == "gaps"
    assert body["unchecked"] == []
    assert body["gaps"] == [
        {
            "ref": "synopsis:1",
            "origin": "synopsis",
            "plan_text": "门外是林晚棠。",
            "basis": "model",
            "missing": [],
            "detail": "梗概写了林晚棠，正文里没有这个人",
            "beat_kind": None,
            "thread_name": None,
        }
    ]
    messages = seen["messages"]
    assert isinstance(messages, list)
    prompt = messages[1]["content"]
    assert "门外是林晚棠。" in prompt
    assert "镜子里是凶手" not in prompt

    async def broken(_messages):
        raise RuntimeError("model down")

    async def resolve_broken(_session):
        return broken

    monkeypatch.setattr(
        plan_check_service,
        "resolve_plan_check_generate",
        resolve_broken,
    )
    fallback = await client.post(f"/api/v1/chapters/{chapter['id']}/plan-check")
    assert fallback.status_code == 200
    assert fallback.json()["source"] == "literal"
    assert fallback.json()["gaps"][0]["basis"] == "literal"
    assert "林晚棠" in fallback.json()["gaps"][0]["missing"]

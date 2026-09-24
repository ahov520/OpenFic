# -*- coding: utf-8 -*-
"""情节线 API，以及它出现在章节上下文里的方式。"""

import json

import pytest
from httpx import AsyncClient

from app.storage.plot_threads import PLOT_PLAN_NOTICE


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
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={"volume_id": volume_id, "title": title, "content": f"{title}正文"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_plot_thread_board_tracks_plant_and_payoff(client: AsyncClient) -> None:
    project_id, volume_id = await _create_project(client)
    first = await _create_chapter(client, project_id, volume_id, "夜航")
    second = await _create_chapter(client, project_id, volume_id, "对上")

    created = await client.post(
        f"/api/v1/projects/{project_id}/plot-threads",
        json={"name": "铜镜", "intent": "灯要在后文对上"},
    )
    assert created.status_code == 201
    thread = created.json()
    assert thread["status"] == "active"
    assert thread["issues"] == ["open"]
    assert thread["last_chapter_id"] is None

    planted = await client.post(
        f"/api/v1/plot-threads/{thread['id']}/beats",
        json={"chapter_id": first["id"], "kind": "plant", "note": "灯还亮着"},
    )
    assert planted.status_code == 201
    assert planted.json()["issues"] == ["open"]
    assert planted.json()["last_chapter_title"] == "夜航"
    assert planted.json()["last_kind"] == "plant"
    assert planted.json()["beats"][0]["global_order"] == 1

    paid = await client.post(
        f"/api/v1/plot-threads/{thread['id']}/beats",
        json={"chapter_id": second["id"], "kind": "payoff", "note": "镜子里是凶手"},
    )
    assert paid.status_code == 201
    paid_thread = paid.json()
    assert [beat["kind"] for beat in paid_thread["beats"]] == ["plant", "payoff"]
    assert paid_thread["last_global_order"] == 2
    assert paid_thread["issues"] == ["payoff_still_active"]

    duplicate = await client.post(
        f"/api/v1/plot-threads/{thread['id']}/beats",
        json={"chapter_id": first["id"], "kind": "advance", "note": "重复"},
    )
    assert duplicate.status_code == 409

    resolved = await client.patch(
        f"/api/v1/plot-threads/{thread['id']}",
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["issues"] == []

    board = await client.get(f"/api/v1/projects/{project_id}/plot-threads")
    assert board.status_code == 200
    body = board.json()
    assert body["threads"][0]["name"] == "铜镜"
    assert [chapter["title"] for chapter in body["chapters"]] == ["夜航", "对上"]


@pytest.mark.asyncio
async def test_plot_thread_flags_payoff_without_plant(client: AsyncClient) -> None:
    project_id, volume_id = await _create_project(client)
    chapter = await _create_chapter(client, project_id, volume_id, "对上")
    created = await client.post(
        f"/api/v1/projects/{project_id}/plot-threads",
        json={"name": "直接收", "intent": "没有先埋"},
    )
    assert created.status_code == 201
    thread_id = created.json()["id"]

    paid = await client.post(
        f"/api/v1/plot-threads/{thread_id}/beats",
        json={"chapter_id": chapter["id"], "kind": "payoff", "note": "忽然说破"},
    )
    assert paid.status_code == 201
    assert paid.json()["issues"] == ["payoff_without_plant", "payoff_still_active"]

    invalid = await client.post(
        f"/api/v1/projects/{project_id}/plot-threads",
        json={"name": "坏状态", "status": "done"},
    )
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_deleting_chapter_drops_its_beat(client: AsyncClient) -> None:
    project_id, volume_id = await _create_project(client)
    first = await _create_chapter(client, project_id, volume_id, "夜航")
    second = await _create_chapter(client, project_id, volume_id, "对上")
    created = await client.post(
        f"/api/v1/projects/{project_id}/plot-threads",
        json={"name": "铜镜", "intent": "灯要在后文对上"},
    )
    thread_id = created.json()["id"]
    await client.post(
        f"/api/v1/plot-threads/{thread_id}/beats",
        json={"chapter_id": first["id"], "kind": "plant", "note": "灯还亮着"},
    )
    await client.post(
        f"/api/v1/plot-threads/{thread_id}/beats",
        json={"chapter_id": second["id"], "kind": "payoff", "note": "镜子里是凶手"},
    )

    deleted = await client.delete(f"/api/v1/chapters/{second['id']}")
    assert deleted.status_code == 204
    board = (await client.get(f"/api/v1/projects/{project_id}/plot-threads")).json()
    thread = board["threads"][0]
    assert [beat["chapter_id"] for beat in thread["beats"]] == [first["id"]]
    assert thread["issues"] == ["open"]
    assert thread["last_kind"] == "plant"


@pytest.mark.asyncio
async def test_chapter_context_includes_plan_without_future_payoff(
    client: AsyncClient,
) -> None:
    project_id, volume_id = await _create_project(client)
    first = await _create_chapter(client, project_id, volume_id, "夜航")
    second = await _create_chapter(client, project_id, volume_id, "旧伤")
    third = await _create_chapter(client, project_id, volume_id, "对上")
    mirror = (
        await client.post(
            f"/api/v1/projects/{project_id}/plot-threads",
            json={"name": "铜镜", "intent": "灯要在后文对上"},
        )
    ).json()
    later = (
        await client.post(
            f"/api/v1/projects/{project_id}/plot-threads",
            json={"name": "旧伤", "intent": "第二卷才提起"},
        )
    ).json()
    await client.post(
        f"/api/v1/plot-threads/{mirror['id']}/beats",
        json={"chapter_id": first["id"], "kind": "plant", "note": "灯还亮着"},
    )
    await client.post(
        f"/api/v1/plot-threads/{mirror['id']}/beats",
        json={"chapter_id": third["id"], "kind": "payoff", "note": "镜子里是凶手"},
    )
    await client.post(
        f"/api/v1/plot-threads/{later['id']}/beats",
        json={"chapter_id": second["id"], "kind": "plant", "note": "伤疤露出来"},
    )

    early = await client.get(
        f"/api/v1/projects/{project_id}/chapter-context/context",
        params={"chapter_id": first["id"]},
    )
    assert early.status_code == 200
    latest = json.loads(early.json()["latest_field"]["content"])
    plan = latest["plot_threads"]
    assert plan["notice"] == PLOT_PLAN_NOTICE
    assert plan["chapter_beats"] == [
        {
            "thread": "铜镜",
            "status": "active",
            "kind": "plant",
            "intent": "灯要在后文对上",
            "note": "灯还亮着",
        }
    ]
    assert plan["open_threads"] == [
        {
            "thread": "铜镜",
            "intent": "灯要在后文对上",
            "last_order": 1,
            "last_title": "夜航",
            "last_kind": "plant",
        }
    ]
    rendered = json.dumps(plan, ensure_ascii=False)
    assert "镜子里是凶手" not in rendered
    assert "旧伤" not in rendered
    assert "作者计划" in plan["notice"]

    closing = await client.get(
        f"/api/v1/projects/{project_id}/chapter-context/context",
        params={"chapter_id": third["id"]},
    )
    closing_plan = json.loads(closing.json()["latest_field"]["content"])["plot_threads"]
    assert closing_plan["chapter_beats"][0]["kind"] == "payoff"
    assert closing_plan["chapter_beats"][0]["note"] == "镜子里是凶手"
    open_names = [item["thread"] for item in closing_plan["open_threads"]]
    assert open_names == ["旧伤"]
    assert "铜镜" not in open_names

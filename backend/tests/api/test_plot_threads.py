# -*- coding: utf-8 -*-
"""情节线 API，以及它出现在章节上下文里的方式。"""

import json

import pytest
from httpx import AsyncClient

from app.storage.plot_threads import CONSIDER_ADVANCE_NOTE, PLOT_PLAN_NOTICE


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
    assert closing_plan["open_threads"][0]["chapters_since"] == 0
    assert "consider_advance" not in closing_plan["open_threads"][0]


@pytest.mark.asyncio
async def test_board_reports_chapters_since_last_and_context_threshold(
    client: AsyncClient,
) -> None:
    project_id, volume_id = await _create_project(client)
    chapters = []
    for title in ("埋下", "二", "三", "四", "五", "结局"):
        chapters.append(await _create_chapter(client, project_id, volume_id, title))

    mirror = (
        await client.post(
            f"/api/v1/projects/{project_id}/plot-threads",
            json={"name": "铜镜", "intent": "还没收"},
        )
    ).json()
    later = (
        await client.post(
            f"/api/v1/projects/{project_id}/plot-threads",
            json={"name": "后文", "intent": "结局才收"},
        )
    ).json()
    done = (
        await client.post(
            f"/api/v1/projects/{project_id}/plot-threads",
            json={"name": "已收", "intent": "收完了", "status": "resolved"},
        )
    ).json()
    await client.post(
        f"/api/v1/plot-threads/{mirror['id']}/beats",
        json={"chapter_id": chapters[0]["id"], "kind": "plant", "note": "灯还亮着"},
    )
    await client.post(
        f"/api/v1/plot-threads/{later['id']}/beats",
        json={"chapter_id": chapters[0]["id"], "kind": "plant", "note": "先埋下"},
    )
    await client.post(
        f"/api/v1/plot-threads/{later['id']}/beats",
        json={
            "chapter_id": chapters[5]["id"],
            "kind": "payoff",
            "note": "镜子里是凶手",
        },
    )
    await client.post(
        f"/api/v1/plot-threads/{done['id']}/beats",
        json={"chapter_id": chapters[0]["id"], "kind": "plant", "note": "埋"},
    )
    await client.post(
        f"/api/v1/plot-threads/{done['id']}/beats",
        json={"chapter_id": chapters[1]["id"], "kind": "payoff", "note": "收"},
    )

    board = (await client.get(f"/api/v1/projects/{project_id}/plot-threads")).json()
    by_name = {item["name"]: item for item in board["threads"]}
    assert by_name["铜镜"]["chapters_since_last"] == 4
    assert by_name["铜镜"]["last_chapter_title"] == "埋下"
    assert [item["id"] for item in by_name["铜镜"]["gap_chapters"]] == [
        chapter["id"] for chapter in chapters[1:5]
    ]
    assert [item["label"] for item in by_name["铜镜"]["gap_chapters"]] == [
        "2. 二",
        "3. 三",
        "4. 四",
        "5. 五",
    ]
    assert by_name["铜镜"]["gap_range"] is None
    assert chapters[0]["id"] not in [
        item["id"] for item in by_name["铜镜"]["gap_chapters"]
    ]
    assert chapters[5]["id"] not in [
        item["id"] for item in by_name["铜镜"]["gap_chapters"]
    ]
    assert by_name["后文"]["chapters_since_last"] is None
    assert by_name["后文"]["gap_chapters"] == []
    assert by_name["后文"]["issues"] == ["payoff_still_active"]
    assert by_name["已收"]["chapters_since_last"] is None
    assert by_name["已收"]["gap_chapters"] == []
    assert by_name["已收"]["issues"] == []

    async def context_for(index: int) -> dict:
        response = await client.get(
            f"/api/v1/projects/{project_id}/chapter-context/context",
            params={"chapter_id": chapters[index]["id"]},
        )
        assert response.status_code == 200
        latest = json.loads(response.json()["latest_field"]["content"])
        return latest["plot_threads"]

    below = await context_for(3)
    below_mirror = next(
        item for item in below["open_threads"] if item["thread"] == "铜镜"
    )
    assert below_mirror["chapters_since"] == 2
    assert "consider_advance" not in below_mirror
    assert below_mirror["chapters_since"] != by_name["铜镜"]["chapters_since_last"]

    at_threshold = await context_for(4)
    stale = next(
        item for item in at_threshold["open_threads"] if item["thread"] == "铜镜"
    )
    assert stale["chapters_since"] == 3
    assert stale["consider_advance"] == CONSIDER_ADVANCE_NOTE
    rendered = json.dumps(at_threshold, ensure_ascii=False)
    assert "镜子里是凶手" not in rendered
    assert "已收" not in rendered


@pytest.mark.asyncio
async def test_gap_chapters_follow_inserts_volumes_and_collapse(
    client: AsyncClient,
) -> None:
    """插进中间的章会进入空章列表；已回收没有空章；跨卷按卷序；超过 4 章才收成范围。"""
    project_id, volume_id = await _create_project(client)
    planted = await _create_chapter(client, project_id, volume_id, "埋下")
    ending = await _create_chapter(client, project_id, volume_id, "结局")
    mirror = (
        await client.post(
            f"/api/v1/projects/{project_id}/plot-threads",
            json={"name": "铜镜", "intent": "还没收"},
        )
    ).json()
    done = (
        await client.post(
            f"/api/v1/projects/{project_id}/plot-threads",
            json={"name": "已收", "intent": "收完了", "status": "resolved"},
        )
    ).json()
    await client.post(
        f"/api/v1/plot-threads/{mirror['id']}/beats",
        json={"chapter_id": planted["id"], "kind": "plant", "note": "灯"},
    )
    await client.post(
        f"/api/v1/plot-threads/{done['id']}/beats",
        json={"chapter_id": planted["id"], "kind": "plant", "note": "埋"},
    )
    await client.post(
        f"/api/v1/plot-threads/{done['id']}/beats",
        json={"chapter_id": ending["id"], "kind": "payoff", "note": "收"},
    )

    def thread_named(board: dict, name: str) -> dict:
        return next(item for item in board["threads"] if item["name"] == name)

    adjacent = (await client.get(f"/api/v1/projects/{project_id}/plot-threads")).json()
    assert thread_named(adjacent, "铜镜")["chapters_since_last"] == 0
    assert thread_named(adjacent, "铜镜")["gap_chapters"] == []
    assert thread_named(adjacent, "铜镜")["gap_range"] is None
    assert thread_named(adjacent, "已收")["gap_chapters"] == []

    inserted = await _create_chapter(client, project_id, volume_id, "插章")
    reordered = await client.post(
        "/api/v1/chapters/reorder",
        json={
            "volume_id": volume_id,
            "chapter_ids": [planted["id"], inserted["id"], ending["id"]],
        },
    )
    assert reordered.status_code == 200
    widened = (await client.get(f"/api/v1/projects/{project_id}/plot-threads")).json()
    mirror_gap = thread_named(widened, "铜镜")["gap_chapters"]
    assert [item["id"] for item in mirror_gap] == [inserted["id"]]
    assert [item["label"] for item in mirror_gap] == ["2. 插章"]
    assert thread_named(widened, "已收")["gap_chapters"] == []

    second = await client.post(
        f"/api/v1/projects/{project_id}/volumes",
        json={"title": "第二卷"},
    )
    assert second.status_code == 201
    finale = await _create_chapter(client, project_id, second.json()["id"], "卷末")
    extra = [
        await _create_chapter(client, project_id, volume_id, title)
        for title in ("甲", "乙", "丙")
    ]
    across = (await client.get(f"/api/v1/projects/{project_id}/plot-threads")).json()
    listed = thread_named(across, "铜镜")
    assert [chapter["title"] for chapter in across["chapters"]] == [
        "埋下",
        "插章",
        "结局",
        "甲",
        "乙",
        "丙",
        "卷末",
    ]
    assert [item["id"] for item in listed["gap_chapters"]] == [
        inserted["id"],
        ending["id"],
        extra[0]["id"],
        extra[1]["id"],
        extra[2]["id"],
    ]
    assert [item["label"] for item in listed["gap_chapters"]] == [
        "2. 插章",
        "3. 结局",
        "4. 甲",
        "5. 乙",
        "6. 丙",
    ]
    assert finale["id"] not in [item["id"] for item in listed["gap_chapters"]]
    assert planted["id"] not in [item["id"] for item in listed["gap_chapters"]]
    assert listed["chapters_since_last"] == 5
    assert listed["gap_range"] == "2. 插章 → 6. 丙"
    assert thread_named(across, "已收")["gap_chapters"] == []
    assert thread_named(across, "已收")["gap_range"] is None

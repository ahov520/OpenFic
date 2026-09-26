# -*- coding: utf-8 -*-
"""
Character Appearance API 测试。
"""

import pytest
from httpx import AsyncClient

from tests.api.test_characters import create_character, create_project


async def _create_chapter(
    client: AsyncClient,
    project_id: str,
    volume_id: str,
    title: str,
    content: str,
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={"volume_id": volume_id, "title": title, "content": content},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_appearance_stats_count_chapters_and_reading_order(
    client: AsyncClient,
) -> None:
    project_id = await create_project(client, "出场统计")
    volumes = (await client.get(f"/api/v1/projects/{project_id}/volumes")).json()
    volume_id = volumes[0]["id"]

    lin = await create_character(client, project_id, "林昭")
    shen = await create_character(client, project_id, "沈砚")
    await create_character(client, project_id, "叶蓁")

    await _create_chapter(client, project_id, volume_id, "第一章", "林昭进城。")
    await _create_chapter(client, project_id, volume_id, "第二章", "沈砚迎面走来。")
    await _create_chapter(client, project_id, volume_id, "第三章", "林昭与沈砚对坐。林昭先开口。")

    response = await client.get(
        f"/api/v1/projects/{project_id}/characters/appearances"
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 3

    # 按出场章数降序，同数按名称稳定排序
    assert [item["name"] for item in items][:2] == ["林昭", "沈砚"]
    top = items[0]
    assert top["character_id"] == lin["id"]
    assert top["chapter_count"] == 2
    assert top["total_chapters"] == 3
    assert abs(top["coverage"] - 2 / 3) < 1e-6
    assert top["first_chapter_title"] == "第一章"
    assert top["last_chapter_title"] == "第三章"

    second = items[1]
    assert second["character_id"] == shen["id"]
    assert second["chapter_count"] == 2
    assert second["first_chapter_title"] == "第二章"

    # 未出场的角色计数为 0，首末章为空
    never = items[2]
    assert never["chapter_count"] == 0
    assert never["first_chapter_id"] is None
    assert never["coverage"] == 0.0


@pytest.mark.asyncio
async def test_appearance_stats_empty_project(client: AsyncClient) -> None:
    project_id = await create_project(client, "空项目出场")

    response = await client.get(
        f"/api/v1/projects/{project_id}/characters/appearances"
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.asyncio
async def test_appearance_stats_rejects_missing_project(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/projects/ghost/characters/appearances")
    assert response.status_code == 404

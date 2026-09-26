# -*- coding: utf-8 -*-
"""
Character Relationship API 测试。
"""

import pytest
from httpx import AsyncClient

from tests.api.test_characters import create_character, create_project


@pytest.mark.asyncio
async def test_create_and_list_relationships(client: AsyncClient) -> None:
    project_id = await create_project(client, "关系测试")
    alice = await create_character(client, project_id, "林昭")
    bob = await create_character(client, project_id, "沈砚")

    created = await client.post(
        f"/api/v1/projects/{project_id}/character-relationships",
        json={
            "character_a_id": alice["id"],
            "character_b_id": bob["id"],
            "relation_type": "敌对",
            "description": "灭门之仇",
        },
    )
    assert created.status_code == 201
    relationship = created.json()
    assert relationship["relation_type"] == "敌对"
    assert relationship["description"] == "灭门之仇"
    # 无方向：字典序较小的角色 ID 存在 from 侧。
    assert {relationship["from_character_id"], relationship["to_character_id"]} == {
        alice["id"],
        bob["id"],
    }

    listed = await client.get(
        f"/api/v1/projects/{project_id}/character-relationships"
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == relationship["id"]


@pytest.mark.asyncio
async def test_create_relationship_dedupes_both_directions(
    client: AsyncClient,
) -> None:
    project_id = await create_project(client, "去重测试")
    alice = await create_character(client, project_id, "林昭")
    bob = await create_character(client, project_id, "沈砚")

    first = await client.post(
        f"/api/v1/projects/{project_id}/character-relationships",
        json={
            "character_a_id": alice["id"],
            "character_b_id": bob["id"],
            "relation_type": "师徒",
        },
    )
    assert first.status_code == 201

    duplicate = await client.post(
        f"/api/v1/projects/{project_id}/character-relationships",
        json={
            "character_a_id": bob["id"],
            "character_b_id": alice["id"],
            "relation_type": "仇敌",
        },
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_create_relationship_rejects_self_and_missing(
    client: AsyncClient,
) -> None:
    project_id = await create_project(client, "校验测试")
    alice = await create_character(client, project_id, "林昭")

    self_related = await client.post(
        f"/api/v1/projects/{project_id}/character-relationships",
        json={"character_a_id": alice["id"], "character_b_id": alice["id"]},
    )
    assert self_related.status_code == 400

    missing = await client.post(
        f"/api/v1/projects/{project_id}/character-relationships",
        json={
            "character_a_id": alice["id"],
            "character_b_id": "ghost-id",
        },
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_update_and_delete_relationship(client: AsyncClient) -> None:
    project_id = await create_project(client, "改删测试")
    alice = await create_character(client, project_id, "林昭")
    bob = await create_character(client, project_id, "沈砚")
    created = await client.post(
        f"/api/v1/projects/{project_id}/character-relationships",
        json={
            "character_a_id": alice["id"],
            "character_b_id": bob["id"],
            "relation_type": "同门",
        },
    )
    relationship_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/character-relationships/{relationship_id}",
        json={"relation_type": "决裂的师兄弟", "description": "第三卷反目"},
    )
    assert updated.status_code == 200
    assert updated.json()["relation_type"] == "决裂的师兄弟"
    assert updated.json()["description"] == "第三卷反目"

    deleted = await client.delete(
        f"/api/v1/character-relationships/{relationship_id}"
    )
    assert deleted.status_code == 204

    listed = await client.get(
        f"/api/v1/projects/{project_id}/character-relationships"
    )
    assert listed.json()["total"] == 0

    missing = await client.delete(
        f"/api/v1/character-relationships/{relationship_id}"
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_deleting_character_removes_its_relationships(
    client: AsyncClient,
) -> None:
    project_id = await create_project(client, "级联测试")
    alice = await create_character(client, project_id, "林昭")
    bob = await create_character(client, project_id, "沈砚")
    carol = await create_character(client, project_id, "叶蓁")

    await client.post(
        f"/api/v1/projects/{project_id}/character-relationships",
        json={
            "character_a_id": alice["id"],
            "character_b_id": bob["id"],
            "relation_type": "搭档",
        },
    )
    second = await client.post(
        f"/api/v1/projects/{project_id}/character-relationships",
        json={
            "character_a_id": bob["id"],
            "character_b_id": carol["id"],
            "relation_type": "母女",
        },
    )
    assert second.status_code == 201

    deleted = await client.delete(f"/api/v1/characters/{bob['id']}")
    assert deleted.status_code == 204

    listed = await client.get(
        f"/api/v1/projects/{project_id}/character-relationships"
    )
    assert listed.json()["total"] == 0


@pytest.mark.asyncio
async def test_create_relationship_rejects_overlong_type(
    client: AsyncClient,
) -> None:
    project_id = await create_project(client, "限长测试")
    alice = await create_character(client, project_id, "林昭")
    bob = await create_character(client, project_id, "沈砚")

    too_long = await client.post(
        f"/api/v1/projects/{project_id}/character-relationships",
        json={
            "character_a_id": alice["id"],
            "character_b_id": bob["id"],
            "relation_type": "亲" * 81,
        },
    )
    assert too_long.status_code == 422

# -*- coding: utf-8 -*-
"""角色关系数据访问。

查询条件全部由 SQLAlchemy 表达式 API 以绑定参数执行，不拼接 SQL 文本。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.storage.models.character_relationship import CharacterRelationship


async def create(
    session: AsyncSession, relationship: CharacterRelationship
) -> CharacterRelationship:
    session.add(relationship)
    await session.flush()
    await session.refresh(relationship)
    return relationship


async def get_by_id(
    session: AsyncSession, relationship_id: str
) -> CharacterRelationship | None:
    result = await session.scalars(
        select(CharacterRelationship).where(
            col(CharacterRelationship.id) == relationship_id
        )
    )
    return result.first()


async def get_between(
    session: AsyncSession, project_id: str, character_a: str, character_b: str
) -> CharacterRelationship | None:
    """按无序对查询两名角色之间的关系（from 存字典序较小者）。"""
    first, second = sorted((character_a, character_b))
    result = await session.scalars(
        select(CharacterRelationship).where(
            col(CharacterRelationship.project_id) == project_id,
            col(CharacterRelationship.from_character_id) == first,
            col(CharacterRelationship.to_character_id) == second,
        )
    )
    return result.first()


async def list_by_project(
    session: AsyncSession, project_id: str
) -> list[CharacterRelationship]:
    result = await session.scalars(
        select(CharacterRelationship)
        .where(col(CharacterRelationship.project_id) == project_id)
        .order_by(col(CharacterRelationship.created_at).asc())
    )
    return list(result.all())


async def list_by_character_id(
    session: AsyncSession, character_id: str
) -> list[CharacterRelationship]:
    """一名角色参与的全部关系（两个方向）。"""
    from_relationships = await session.scalars(
        select(CharacterRelationship).where(
            col(CharacterRelationship.from_character_id) == character_id
        )
    )
    to_relationships = await session.scalars(
        select(CharacterRelationship).where(
            col(CharacterRelationship.to_character_id) == character_id
        )
    )
    merged = {relationship.id: relationship for relationship in from_relationships}
    for relationship in to_relationships:
        merged.setdefault(relationship.id, relationship)
    return list(merged.values())


async def save(
    session: AsyncSession, relationship: CharacterRelationship
) -> CharacterRelationship:
    session.add(relationship)
    await session.flush()
    await session.refresh(relationship)
    return relationship


async def delete(session: AsyncSession, relationship: CharacterRelationship) -> None:
    await session.delete(relationship)
    await session.flush()


async def delete_by_character_ids(
    session: AsyncSession, character_ids: list[str]
) -> None:
    """删除涉及给定角色的全部关系（角色删除时随行清理）。"""
    seen_ids: set[str] = set()
    for character_id in character_ids:
        for relationship in await list_by_character_id(session, character_id):
            if relationship.id in seen_ids:
                continue
            seen_ids.add(relationship.id)
            await delete(session, relationship)


async def delete_by_project(session: AsyncSession, project_id: str) -> None:
    for relationship in await list_by_project(session, project_id):
        await delete(session, relationship)

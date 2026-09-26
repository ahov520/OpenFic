# -*- coding: utf-8 -*-
"""角色关系业务：创建、更新、删除与列出。"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.storage.models.character_relationship import CharacterRelationship
from app.storage.repos import character_relationship_repo, character_repo

RELATION_TYPE_MAX_LENGTH = 80
RELATION_DESCRIPTION_MAX_LENGTH = 2000


def normalize_relation_type(value: str | None) -> str:
    """规范化关系类型：去空白、限制长度。"""
    text = (value or "").strip()
    if len(text) > RELATION_TYPE_MAX_LENGTH:
        raise ValueError(f"关系类型超出 {RELATION_TYPE_MAX_LENGTH} 字限制")
    return text


def normalize_description(value: str | None) -> str:
    """规范化关系说明：统一换行、限制长度。"""
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > RELATION_DESCRIPTION_MAX_LENGTH:
        raise ValueError(f"关系说明超出 {RELATION_DESCRIPTION_MAX_LENGTH} 字限制")
    return text


async def _require_character(
    session: AsyncSession, project_id: str, character_id: str
) -> None:
    character = await character_repo.get_by_id(session, character_id)
    if character is None or character.project_id != project_id:
        raise NotFoundError(f"角色不存在: {character_id}")


async def create_relationship(
    session: AsyncSession,
    project_id: str,
    character_a_id: str,
    character_b_id: str,
    relation_type: str,
    description: str = "",
) -> CharacterRelationship:
    """
    在两名角色之间建立一条关系。

    关系无方向，存储时把字典序较小的角色 ID 放在 from_character_id。
    同一对角色只允许一条关系；重复创建抛 ConflictError。

    Raises:
        NotFoundError: 角色不存在或不属于该项目。
        ValueError: 两名角色相同，或字段超长。
        ConflictError: 这两名角色之间已有关系。
    """
    if character_a_id == character_b_id:
        raise ValueError("不能给同一名角色建立关系")
    await _require_character(session, project_id, character_a_id)
    await _require_character(session, project_id, character_b_id)

    existing = await character_relationship_repo.get_between(
        session, project_id, character_a_id, character_b_id
    )
    if existing is not None:
        raise ConflictError("这两名角色之间已存在关系")

    first, second = sorted((character_a_id, character_b_id))
    relationship = CharacterRelationship(
        project_id=project_id,
        from_character_id=first,
        to_character_id=second,
        relation_type=normalize_relation_type(relation_type),
        description=normalize_description(description),
    )
    return await character_relationship_repo.create(session, relationship)


async def get_relationship(
    session: AsyncSession, relationship_id: str
) -> CharacterRelationship:
    relationship = await character_relationship_repo.get_by_id(
        session, relationship_id
    )
    if relationship is None:
        raise NotFoundError(f"角色关系不存在: {relationship_id}")
    return relationship


async def list_relationships(
    session: AsyncSession, project_id: str
) -> list[CharacterRelationship]:
    return await character_relationship_repo.list_by_project(session, project_id)


async def update_relationship(
    session: AsyncSession,
    relationship_id: str,
    relation_type: str | None = None,
    description: str | None = None,
) -> CharacterRelationship:
    """更新关系的类型或说明。传入 None 表示保持不变。"""
    relationship = await get_relationship(session, relationship_id)

    changed = False
    if relation_type is not None:
        normalized = normalize_relation_type(relation_type)
        if normalized != relationship.relation_type:
            relationship.relation_type = normalized
            changed = True
    if description is not None:
        normalized = normalize_description(description)
        if normalized != relationship.description:
            relationship.description = normalized
            changed = True

    if changed:
        relationship.updated_at = datetime.now(UTC)
        relationship = await character_relationship_repo.save(session, relationship)
    return relationship


async def delete_relationship(session: AsyncSession, relationship_id: str) -> None:
    relationship = await get_relationship(session, relationship_id)
    await character_relationship_repo.delete(session, relationship)


async def cleanup_for_deleted_characters(
    session: AsyncSession, character_ids: list[str]
) -> None:
    """角色被删除时清掉挂在它们身上的关系。"""
    await character_relationship_repo.delete_by_character_ids(session, character_ids)


async def cleanup_for_deleted_project(
    session: AsyncSession, project_id: str
) -> None:
    """项目被删除时清掉项目内的全部关系。"""
    await character_relationship_repo.delete_by_project(session, project_id)

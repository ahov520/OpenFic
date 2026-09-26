# -*- coding: utf-8 -*-
"""Character Relationship Router - 角色关系 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.character import (
    CharacterRelationshipCreate,
    CharacterRelationshipListResponse,
    CharacterRelationshipResponse,
    CharacterRelationshipUpdate,
)
from app.core.errors import ConflictError, NotFoundError
from app.storage.database import get_session
from app.storage.services import character_relationship_service

router = APIRouter(tags=["character-relationships"])


@router.get(
    "/projects/{project_id}/character-relationships",
    response_model=CharacterRelationshipListResponse,
    summary="列出项目内全部角色关系",
)
async def list_character_relationships(
    project_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CharacterRelationshipListResponse:
    relationships = await character_relationship_service.list_relationships(
        session, project_id
    )
    items = [
        CharacterRelationshipResponse.model_validate(relationship)
        for relationship in relationships
    ]
    return CharacterRelationshipListResponse(items=items, total=len(items))


@router.post(
    "/projects/{project_id}/character-relationships",
    response_model=CharacterRelationshipResponse,
    status_code=status.HTTP_201_CREATED,
    summary="在两名角色之间建立关系",
)
async def create_character_relationship(
    project_id: str,
    data: CharacterRelationshipCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CharacterRelationshipResponse:
    try:
        relationship = await character_relationship_service.create_relationship(
            session,
            project_id,
            data.character_a_id,
            data.character_b_id,
            data.relation_type,
            data.description,
        )
        return CharacterRelationshipResponse.model_validate(relationship)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch(
    "/character-relationships/{relationship_id}",
    response_model=CharacterRelationshipResponse,
    summary="更新角色关系",
)
async def update_character_relationship(
    relationship_id: str,
    data: CharacterRelationshipUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CharacterRelationshipResponse:
    try:
        logger.info(f"更新角色关系: {relationship_id}")
        relationship = await character_relationship_service.update_relationship(
            session,
            relationship_id,
            relation_type=data.relation_type,
            description=data.description,
        )
        return CharacterRelationshipResponse.model_validate(relationship)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/character-relationships/{relationship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除角色关系",
)
async def delete_character_relationship(
    relationship_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    try:
        logger.info(f"删除角色关系: {relationship_id}")
        await character_relationship_service.delete_relationship(
            session, relationship_id
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

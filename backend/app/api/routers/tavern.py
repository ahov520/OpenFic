"""Import SillyTavern writing materials into a project."""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.tavern import (
    TavernBlockPreview,
    TavernImportResponse,
    TavernLorePreview,
    TavernPreviewResponse,
)
from app.core.errors import NotFoundError
from app.storage.database import get_session
from app.storage.services import tavern_import_service

router = APIRouter(tags=["tavern"])

MAX_IMPORT_FILE_SIZE = 15 * 1024 * 1024


def _preview_response(preview: tavern_import_service.TavernPreview) -> TavernPreviewResponse:
    constant_count = sum(1 for entry in preview.lore_entries if entry.is_constant)
    keyword_count = sum(1 for entry in preview.lore_entries if entry.keywords and not entry.is_constant)
    return TavernPreviewResponse(
        kind=preview.kind,
        character_name=preview.character_name,
        description_preview=preview.description_preview,
        discarded=preview.discarded,
        constant_count=constant_count,
        keyword_count=keyword_count,
        lore_entries=[
            TavernLorePreview(
                name=entry.name,
                keywords=entry.keywords,
                is_constant=entry.is_constant,
                is_enabled=entry.is_enabled,
            )
            for entry in preview.lore_entries[:80]
        ],
        preset_name=preview.preset_name,
        blocks=[
            TavernBlockPreview(
                block_id=block.block_id,
                name=block.name,
                content_preview=block.content[:240],
                bucket=block.bucket,
                reason=block.reason,
                included=block.bucket != "discarded",
            )
            for block in preview.blocks
        ],
    )


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    filename = file.filename or ""
    lowered = filename.lower()
    if not lowered.endswith((".json", ".png")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 .json 或 .png 文件")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件内容为空")
    if len(content) > MAX_IMPORT_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件大小超过限制（最大 15MB）")
    return content, filename


def _included_ids(raw: str) -> set[str] | None:
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="included_block_ids 不是合法 JSON") from exc
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="included_block_ids 必须是字符串数组")
    return set(payload)


@router.post(
    "/projects/{project_id}/tavern/preview",
    response_model=TavernPreviewResponse,
    summary="预览酒馆素材",
)
async def preview_tavern_material(
    project_id: str,
    file: Annotated[UploadFile, File(description="角色卡、世界书或预设")],
    user_name: Annotated[str, Form()] = "",
) -> TavernPreviewResponse:
    """Parse a tavern file and show what will be kept."""
    _ = project_id
    content, filename = await _read_upload(file)
    try:
        preview = tavern_import_service.preview_material(content, filename=filename, user_name=user_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _preview_response(preview)


@router.post(
    "/projects/{project_id}/tavern/import",
    response_model=TavernImportResponse,
    summary="导入酒馆素材",
)
async def import_tavern_material(
    project_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    file: Annotated[UploadFile, File(description="角色卡、世界书或预设")],
    user_name: Annotated[str, Form()] = "",
    mode: Annotated[Literal["append", "overwrite"], Form()] = "append",
    included_block_ids: Annotated[str, Form()] = "",
) -> TavernImportResponse:
    """Write the confirmed tavern file into the project."""
    content, filename = await _read_upload(file)
    try:
        result = await tavern_import_service.import_material(
            session,
            project_id=project_id,
            raw=content,
            filename=filename,
            user_name=user_name,
            mode=mode,
            included_block_ids=_included_ids(included_block_ids),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TavernImportResponse(
        kind=result.kind,
        character_id=result.character_id,
        imported_entries=result.imported_entries,
        imported_rules=result.imported_rules,
        imported_skills=result.imported_skills,
    )

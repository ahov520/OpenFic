# -*- coding: utf-8 -*-
"""
Sensitive Words Router - 敏感词/平台违禁词词库 API。

词表存 Setting 键值表；首次读取惰性 seed 内置首发词库，
支持 TXT/JSON 导入导出与整表更新，全程本地零网络。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.sensitive_words import (
    SensitiveWordEntry,
    SensitiveWordsExportResponse,
    SensitiveWordsImportRequest,
    SensitiveWordsListResponse,
    SensitiveWordsUpdateRequest,
)
from app.core.sensitive_words import (
    SensitiveWordError,
    get_words,
    normalize_words,
    parse_import_content,
    save_words,
    words_to_json,
    words_to_txt,
)
from app.storage.database import get_session

router = APIRouter(tags=["sensitive-words"])


@router.get(
    "/sensitive-words",
    response_model=SensitiveWordsListResponse,
    summary="获取敏感词词表（首次读取惰性 seed 内置首发词库）",
)
async def list_sensitive_words(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SensitiveWordsListResponse:
    words = await get_words(session)
    entries = [SensitiveWordEntry.model_validate(entry) for entry in words]
    return SensitiveWordsListResponse(words=entries, count=len(entries))


@router.put(
    "/sensitive-words",
    response_model=SensitiveWordsListResponse,
    summary="整表更新敏感词词表",
)
async def update_sensitive_words(
    data: SensitiveWordsUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SensitiveWordsListResponse:
    words, stats = normalize_words([entry.model_dump() for entry in data.words])
    saved = await save_words(session, words, normalized=True)
    entries = [SensitiveWordEntry.model_validate(entry) for entry in saved]
    return SensitiveWordsListResponse(words=entries, count=len(entries), stats=stats)


@router.post(
    "/sensitive-words/import",
    response_model=SensitiveWordsListResponse,
    summary="导入敏感词（TXT/JSON，与现有词表按词去重合并）",
)
async def import_sensitive_words(
    data: SensitiveWordsImportRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SensitiveWordsListResponse:
    existing = await get_words(session)
    try:
        raw_entries = parse_import_content(data.content, data.format)
    except SensitiveWordError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    imported, stats = normalize_words([*existing, *raw_entries])
    added = len(imported) - len(existing)
    saved = await save_words(session, imported, normalized=True)
    entries = [SensitiveWordEntry.model_validate(entry) for entry in saved]
    return SensitiveWordsListResponse(
        words=entries,
        count=len(entries),
        stats={"accepted": added, "duplicates": stats["duplicates"], "invalid": stats["invalid"]},
    )


@router.get(
    "/sensitive-words/export",
    response_model=SensitiveWordsExportResponse,
    summary="导出敏感词词表（TXT/JSON）",
)
async def export_sensitive_words(
    format: Annotated[str, Query(pattern="^(txt|json)$")] = "txt",
    session: AsyncSession = Depends(get_session),
) -> SensitiveWordsExportResponse:
    words = await get_words(session)
    if format == "json":
        content = words_to_json(words)
    else:
        content = words_to_txt(words)
    return SensitiveWordsExportResponse(
        filename=f"sensitive-words.{format}",
        format=format,
        content=content,
    )

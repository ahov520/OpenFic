# -*- coding: utf-8 -*-
"""贴在选中原文上的旁注。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.margin_note import (
    MarginNoteCreate,
    MarginNoteResponse,
    MarginNoteUpdate,
    OpenMarginNoteResponse,
)
from app.background.jobs import service as background_service
from app.core.errors import NotFoundError
from app.storage.database import get_session
from app.storage.margin_notes import mark_kind
from app.storage.services import margin_note_service
from app.storage.services.margin_note_service import MarginNoteView

router = APIRouter(tags=["margin-notes"])


def _response(view: MarginNoteView) -> MarginNoteResponse:
    note = view.note
    status = "struck" if note.status == "struck" else "open"
    return MarginNoteResponse(
        id=note.id,
        chapter_id=note.chapter_id,
        anchor_text=note.anchor_text,
        context_before=note.context_before,
        context_after=note.context_after,
        body=note.body,
        status=status,
        alignment="aligned" if view.aligned else "misaligned",
        mark=mark_kind(status, view.aligned),
        start=view.start,
        end=view.end,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.get(
    "/projects/{project_id}/margin-notes",
    response_model=list[OpenMarginNoteResponse],
    summary="列出全书未划掉的旁注",
)
async def list_open_margin_notes(
    project_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[OpenMarginNoteResponse]:
    notes = await margin_note_service.list_open_margin_notes(session, project_id)
    return [
        OpenMarginNoteResponse(
            id=note.id,
            chapter_id=note.chapter_id,
            chapter_title=note.chapter_title,
            anchor_text=note.anchor_text,
            body=note.body,
            created_at=note.created_at,
        )
        for note in notes
    ]


@router.get(
    "/chapters/{chapter_id}/margin-notes",
    response_model=list[MarginNoteResponse],
    summary="列出这一章的旁注",
)
async def list_margin_notes(
    chapter_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[MarginNoteResponse]:
    try:
        notes = await margin_note_service.list_margin_notes(session, chapter_id)
        return [_response(note) for note in notes]
    except NotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.post(
    "/chapters/{chapter_id}/margin-notes",
    response_model=MarginNoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="给选中的原文记一条旁注",
)
async def create_margin_note(
    chapter_id: str,
    data: MarginNoteCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MarginNoteResponse:
    try:
        view = await margin_note_service.create_margin_note(
            session,
            chapter_id,
            anchor_text=data.anchor_text,
            context_before=data.context_before,
            context_after=data.context_after,
            body=data.body,
        )
        await background_service.commit_and_notify(session)
        return _response(view)
    except NotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.patch(
    "/chapters/{chapter_id}/margin-notes/{note_id}",
    response_model=MarginNoteResponse,
    summary="划掉、改写或改钉旁注",
)
async def update_margin_note(
    chapter_id: str,
    note_id: str,
    data: MarginNoteUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MarginNoteResponse:
    try:
        view = await margin_note_service.update_margin_note(
            session,
            chapter_id,
            note_id,
            status=data.status,
            body=data.body,
            anchor_text=data.anchor_text,
            context_before=data.context_before,
            context_after=data.context_after,
        )
        await background_service.commit_and_notify(session)
        return _response(view)
    except NotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.delete(
    "/chapters/{chapter_id}/margin-notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除旁注",
)
async def delete_margin_note(
    chapter_id: str,
    note_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    try:
        await margin_note_service.delete_margin_note(session, chapter_id, note_id)
        await background_service.commit_and_notify(session)
    except NotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))

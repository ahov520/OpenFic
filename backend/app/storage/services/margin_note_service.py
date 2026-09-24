# -*- coding: utf-8 -*-
"""章节旁注。写入旁注时不改章节正文，也不改字数。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.storage.margin_notes import (
    agent_margin_payload,
    locate_anchor,
    normalize_anchor,
    normalize_body,
    normalize_context,
    normalize_status,
)
from app.storage.models.margin_note import ChapterMarginNote
from app.storage.repos import chapter_repo, margin_note_repo


@dataclass(frozen=True)
class MarginNoteView:
    note: ChapterMarginNote
    aligned: bool
    start: int | None
    end: int | None


def _view(note: ChapterMarginNote, content: str) -> MarginNoteView:
    hit = locate_anchor(
        content, note.anchor_text, note.context_before, note.context_after
    )
    return MarginNoteView(note=note, aligned=hit.aligned, start=hit.start, end=hit.end)


async def _chapter_or_raise(session: AsyncSession, chapter_id: str):
    chapter = await chapter_repo.get_by_id(session, chapter_id)
    if chapter is None:
        raise NotFoundError("章节不存在")
    return chapter


async def list_margin_notes(
    session: AsyncSession, chapter_id: str
) -> list[MarginNoteView]:
    chapter = await _chapter_or_raise(session, chapter_id)
    notes = await margin_note_repo.list_by_chapter(session, chapter_id)
    return [_view(note, chapter.content) for note in notes]


async def create_margin_note(
    session: AsyncSession,
    chapter_id: str,
    *,
    anchor_text: str,
    context_before: str,
    context_after: str,
    body: str,
) -> MarginNoteView:
    chapter = await _chapter_or_raise(session, chapter_id)
    note = ChapterMarginNote(
        project_id=chapter.project_id,
        chapter_id=chapter.id,
        anchor_text=normalize_anchor(anchor_text),
        context_before=normalize_context(context_before, keep_end=True),
        context_after=normalize_context(context_after, keep_end=False),
        body=normalize_body(body),
    )
    note = await margin_note_repo.create(session, note)
    return _view(note, chapter.content)


async def update_margin_note(
    session: AsyncSession,
    chapter_id: str,
    note_id: str,
    *,
    status: str | None = None,
    body: str | None = None,
    anchor_text: str | None = None,
    context_before: str | None = None,
    context_after: str | None = None,
) -> MarginNoteView:
    chapter = await _chapter_or_raise(session, chapter_id)
    note = await margin_note_repo.get_by_id(session, note_id)
    if note is None or note.chapter_id != chapter_id:
        raise NotFoundError("旁注不存在")
    changed = False
    if status is not None:
        normalized = normalize_status(status)
        if normalized != note.status:
            note.status = normalized
            changed = True
    if body is not None:
        normalized_body = normalize_body(body)
        if normalized_body != note.body:
            note.body = normalized_body
            changed = True
    if anchor_text is not None:
        # 先校验再写入，空选区失败时不要改掉原来的锚。
        next_anchor = normalize_anchor(anchor_text)
        next_before = normalize_context(context_before or "", keep_end=True)
        next_after = normalize_context(context_after or "", keep_end=False)
        if (
            next_anchor != note.anchor_text
            or next_before != note.context_before
            or next_after != note.context_after
        ):
            note.anchor_text = next_anchor
            note.context_before = next_before
            note.context_after = next_after
            changed = True
    if changed:
        note.updated_at = datetime.now(UTC)
        note = await margin_note_repo.save(session, note)
    return _view(note, chapter.content)


async def delete_margin_note(
    session: AsyncSession, chapter_id: str, note_id: str
) -> None:
    await _chapter_or_raise(session, chapter_id)
    note = await margin_note_repo.get_by_id(session, note_id)
    if note is None or note.chapter_id != chapter_id:
        raise NotFoundError("旁注不存在")
    await margin_note_repo.delete(session, note)


async def margin_notes_for_agent(
    session: AsyncSession, chapter_id: str
) -> dict[str, object] | None:
    """当前章未划掉的旁注。调用方必须把它放在正文之外。"""
    notes = await margin_note_repo.list_by_chapter(session, chapter_id)
    return agent_margin_payload(notes)

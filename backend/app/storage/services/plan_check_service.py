# -*- coding: utf-8 -*-
"""把对照计划检查存到章节上，并走现有的后台模型解析。

没有可用模型或钥匙时，改用字面锚点，不另接供应商。
正文、梗概或本章节拍变化后，已保存的结果标成过期，直到作者再检查一次。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.storage.models.chapter import Chapter
from app.storage.plan_coverage import (
    BeatInput,
    CoverageGap,
    PlanItem,
    PresentedCheck,
    StoredPlanCheck,
    UncheckedLine,
    build_plan_items,
    dump_payload,
    has_author_plan,
    literal_report,
    load_payload,
    parse_model_gaps,
    plan_fingerprint,
    present_check,
    render_check_prompt,
)
from app.storage.repos import chapter_repo, plot_beat_repo, plot_thread_repo

PlanCheckGenerate = Callable[[list[dict[str, str]]], Awaitable[str]]


async def get_plan_check(session: AsyncSession, chapter_id: str) -> PresentedCheck:
    chapter = await _get_chapter(session, chapter_id)
    fingerprint, has_plan = await _current_inputs(session, chapter)
    return present_check(
        _stored_from_chapter(chapter),
        fingerprint=fingerprint,
        has_plan=has_plan,
    )


async def run_plan_check(session: AsyncSession, chapter_id: str) -> PresentedCheck:
    generate = await resolve_plan_check_generate(session)
    return await run_plan_check_with_generate(session, chapter_id, generate)


async def run_plan_check_with_generate(
    session: AsyncSession,
    chapter_id: str,
    generate: PlanCheckGenerate | None,
) -> PresentedCheck:
    chapter = await _get_chapter(session, chapter_id)
    beats, fingerprint, items, has_plan = await _load_plan(session, chapter)
    del beats
    if not has_plan:
        source = "empty"
        gaps: list[CoverageGap] = []
        unchecked: list[UncheckedLine] = []
    else:
        source, gaps, unchecked = await _evaluate(chapter.content, items, generate)
    checked_at = datetime.now(UTC)
    chapter.plan_check_fingerprint = fingerprint
    chapter.plan_check_source = source
    chapter.plan_check_payload = dump_payload(gaps, unchecked)
    chapter.plan_check_at = checked_at
    await chapter_repo.update_chapter(session, chapter)
    stored = StoredPlanCheck(
        fingerprint=fingerprint,
        source=source,
        gaps=tuple(gaps),
        unchecked=tuple(unchecked),
        checked_at=checked_at,
    )
    return present_check(stored, fingerprint=fingerprint, has_plan=has_plan)


async def resolve_plan_check_generate(
    session: AsyncSession,
) -> PlanCheckGenerate | None:
    """复用摘要那条模型解析和 LLMClient。没有模型或钥匙时返回空。"""
    from app.background.llm.resolver import (
        BackgroundModelUnavailableError,
        resolve_background_llm,
    )
    from app.memory.summary_config import resolve_summary_model_id

    try:
        model_id = await resolve_summary_model_id(session)
        if not model_id:
            return None
        resolved = await resolve_background_llm(
            session,
            model_policy="summary_model",
            model_id=model_id,
        )
    except BackgroundModelUnavailableError:
        return None
    except Exception as error:
        logger.warning(f"对照计划检查没有可用模型: {error}")
        return None
    if not resolved.client.config.api_key.strip():
        return None

    async def generate(messages: list[dict[str, str]]) -> str:
        response = await resolved.client.generate(messages, timeout=90)
        return response.content

    return generate


async def _evaluate(
    prose: str,
    items: list[PlanItem],
    generate: PlanCheckGenerate | None,
) -> tuple[str, list[CoverageGap], list[UncheckedLine]]:
    if generate is not None:
        try:
            raw = await generate(render_check_prompt(prose, items))
        except Exception as error:
            logger.warning(f"对照计划检查的模型调用失败，改用字面检查: {error}")
            raw = None
        if raw:
            parsed = parse_model_gaps(raw, items)
            if parsed is not None:
                return "model", parsed, []
            logger.warning("对照计划检查的模型结果无法对应到计划，改用字面检查")
    gaps, unchecked = literal_report(prose, items)
    return "literal", gaps, unchecked


async def _current_inputs(session: AsyncSession, chapter: Chapter) -> tuple[str, bool]:
    _beats, fingerprint, _items, has_plan = await _load_plan(session, chapter)
    return fingerprint, has_plan


async def _load_plan(
    session: AsyncSession,
    chapter: Chapter,
) -> tuple[list[BeatInput], str, list[PlanItem], bool]:
    rows = await plot_beat_repo.list_by_chapter(session, chapter.id)
    threads = await plot_thread_repo.list_by_project(session, chapter.project_id)
    by_id = {thread.id: thread for thread in threads}
    beats: list[BeatInput] = []
    for row in rows:
        if row.chapter_id != chapter.id:
            continue
        thread = by_id.get(row.thread_id)
        if thread is None or thread.project_id != chapter.project_id:
            continue
        beats.append(
            BeatInput(
                id=row.id,
                kind=row.kind,
                note=row.note,
                thread_name=thread.name,
                intent=thread.intent,
            )
        )
    return (
        beats,
        plan_fingerprint(chapter.content, chapter.synopsis, beats),
        build_plan_items(chapter.synopsis, beats),
        has_author_plan(chapter.synopsis, beats),
    )


def _stored_from_chapter(chapter: Chapter) -> StoredPlanCheck | None:
    if not chapter.plan_check_fingerprint or not chapter.plan_check_source:
        return None
    if chapter.plan_check_source not in {"model", "literal", "empty"}:
        return None
    loaded = load_payload(chapter.plan_check_payload)
    if loaded is None:
        return None
    gaps, unchecked = loaded
    return StoredPlanCheck(
        fingerprint=chapter.plan_check_fingerprint,
        source=chapter.plan_check_source,
        gaps=gaps,
        unchecked=unchecked,
        checked_at=chapter.plan_check_at,
    )


async def _get_chapter(session: AsyncSession, chapter_id: str) -> Chapter:
    chapter = await chapter_repo.get_by_id(session, chapter_id)
    if chapter is None:
        raise NotFoundError(f"章节不存在: {chapter_id}")
    return chapter

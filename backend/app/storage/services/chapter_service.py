# -*- coding: utf-8 -*-
"""
Chapter Service - 章节业务逻辑层。
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.editor_content_limits import validate_editor_content
from app.core.errors import NotFoundError
from app.memory.chapter.sequence import global_order_index
from app.storage.chapter_length import normalize_word_count_target
from app.storage.chapter_plan import (
    SYNOPSIS_MAX_LENGTH,
    normalize_synopsis,
    normalize_writing_status,
)
from app.storage.models.chapter import Chapter
from app.storage.models.volume import Volume
from app.storage.repos import (
    chapter_repo,
    chapter_summary_repo,
    margin_note_repo,
    plot_beat_repo,
    project_repo,
    volume_repo,
)
from app.storage.services import manual_revision_service, writing_activity_service

UNSET = object()


@dataclass
class VolumeChapterGroup:
    """卷与其章节列表。"""

    volume: Volume
    chapters: list[Chapter]


@dataclass
class VolumeTreeResult:
    """卷-章树结果。"""

    volumes: list[VolumeChapterGroup]
    total_chapters: int
    open_margin_note_counts: dict[str, int]


@dataclass(frozen=True)
class MentionCandidate:
    """对话 mention 候选项。"""

    kind: Literal["volume", "chapter"]
    id: str
    title: str
    label: str
    description: str | None = None


def _count_words(text: str) -> int:
    """
    计算中英文混合文本的字数。

    中文按字符计数，英文按单词计数。

    Args:
        text: 待计算的文本。

    Returns:
        字数。
    """
    if not text:
        return 0

    # 匹配中文字符
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    chinese_count = len(chinese_chars)

    # 移除中文字符后，按空格分割计算英文单词
    text_without_chinese = re.sub(r"[\u4e00-\u9fff]", " ", text)
    english_words = [w for w in text_without_chinese.split() if w.strip()]
    english_count = len(english_words)

    return chinese_count + english_count


def _display_volume_title(volume: Volume) -> str:
    title = volume.title.strip()
    return title or "未命名卷"


def _display_chapter_title(chapter: Chapter) -> str:
    title = chapter.title.strip()
    return title or "未命名章节"


def _match_rank(text: str, normalized_query: str) -> int:
    normalized_text = text.strip().lower()
    if not normalized_text:
        return 99
    if normalized_text == normalized_query:
        return 0
    if normalized_text.startswith(normalized_query):
        return 1
    if normalized_query in normalized_text:
        return 2
    return 99


async def _update_project_stats(session: AsyncSession, project_id: str) -> None:
    """
    更新项目的统计信息（字数和章节数）。

    Args:
        session: 数据库 session。
        project_id: 项目 ID。
    """
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        return

    # 更新章节数
    chapter_count = await chapter_repo.count_by_project(session, project_id)
    project.chapter_count = chapter_count

    # 更新总字数
    total_word_count = await chapter_repo.get_total_word_count(session, project_id)
    project.word_count = total_word_count

    project.updated_at = datetime.now(UTC)
    await project_repo.update(session, project)


async def _update_volume_stats(session: AsyncSession, volume_id: str) -> None:
    """更新卷的章节数缓存。"""
    volume = await volume_repo.get_by_id(session, volume_id)
    if volume is None:
        return
    volume.chapter_count = await chapter_repo.count_by_volume(session, volume_id)
    volume.updated_at = datetime.now(UTC)
    await volume_repo.update_volume(session, volume)


async def create_chapter(
    session: AsyncSession,
    project_id: str,
    volume_id: str,
    title: str,
    content: str = "",
    word_count: int | None = None,
    synopsis: str = "",
    writing_status: str | None = None,
    word_count_target: int | None = None,
) -> Chapter:
    """
    创建章节。

    Args:
        session: 数据库 session。
        project_id: 项目 ID。
        volume_id: 卷 ID。
        title: 章节标题。
        content: 章节内容，默认为空。
        word_count: 字数（前端计算），如果为 None 则后端计算。
        synopsis: 作者梗概。
        writing_status: 写作状态。
        word_count_target: 本章目标字数。空表示不设目标。

    Returns:
        创建的章节实例。

    Raises:
        NotFoundError: 项目不存在。
    """
    validate_editor_content(content)
    synopsis = normalize_synopsis(synopsis)
    writing_status = normalize_writing_status(writing_status)
    word_count_target = normalize_word_count_target(word_count_target)

    # 检查项目是否存在
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")
    volume = await volume_repo.get_by_id(session, volume_id)
    if volume is None or volume.project_id != project_id:
        raise NotFoundError(f"卷不存在: {volume_id}")

    # 获取最大排序序号
    max_order = await chapter_repo.get_max_order(session, volume_id)

    # 使用前端传递的字数，或后端计算
    final_word_count = word_count if word_count is not None else _count_words(content)

    # 创建章节
    chapter = Chapter(
        project_id=project_id,
        volume_id=volume_id,
        title=title,
        content=content,
        synopsis=synopsis,
        writing_status=writing_status,
        word_count=final_word_count,
        word_count_target=word_count_target,
        order=max_order + 1,
    )
    chapter = await chapter_repo.create(session, chapter)

    await writing_activity_service.record_activity(
        session,
        project_id=project_id,
        chapter_id=chapter.id,
        chapter_title=chapter.title,
        source="user",
        operation="create",
        old_word_count=0,
        new_word_count=chapter.word_count,
    )

    # 更新项目统计
    await _update_volume_stats(session, volume_id)
    await _update_project_stats(session, project_id)

    from app.memory.chapter.summary_service import (
        maybe_enqueue_chapter_summary_for_new_chapter,
    )

    await maybe_enqueue_chapter_summary_for_new_chapter(session, chapter)

    from app.retrieval.chapter_index import safe_maybe_enqueue_auto_index
    from app.retrieval.index_status import schedule_emit_index_status

    await safe_maybe_enqueue_auto_index(session, project_id=project_id)
    schedule_emit_index_status(session, project_id)

    return chapter


async def get_chapter(session: AsyncSession, chapter_id: str) -> Chapter:
    """
    获取章节。

    Args:
        session: 数据库 session。
        chapter_id: 章节 ID。

    Returns:
        章节实例。

    Raises:
        NotFoundError: 章节不存在。
    """
    chapter = await chapter_repo.get_by_id(session, chapter_id)
    if chapter is None:
        raise NotFoundError(f"章节不存在: {chapter_id}")
    return chapter


async def list_chapters(
    session: AsyncSession,
    project_id: str,
) -> VolumeTreeResult:
    """
    获取项目卷-章树（章节不含正文内容）。

    Args:
        session: 数据库 session。
        project_id: 项目 ID。

    Returns:
        章节列表结果。

    Raises:
        NotFoundError: 项目不存在。
    """
    # 检查项目是否存在
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")

    volumes = await volume_repo.list_by_project(session, project_id)
    chapters = await chapter_repo.list_metadata_by_project(session, project_id)
    open_margin_note_counts = await margin_note_repo.count_open_by_project(
        session, project_id
    )
    chapters_by_volume: dict[str, list[Chapter]] = {volume.id: [] for volume in volumes}
    for chapter in chapters:
        chapters_by_volume.setdefault(chapter.volume_id, []).append(chapter)
    groups = [
        VolumeChapterGroup(
            volume=volume,
            chapters=chapters_by_volume.get(volume.id, []),
        )
        for volume in volumes
    ]
    return VolumeTreeResult(
        volumes=groups,
        total_chapters=len(chapters),
        open_margin_note_counts=open_margin_note_counts,
    )


async def search_mention_candidates(
    session: AsyncSession,
    project_id: str,
    query: str,
    *,
    limit: int = 20,
) -> list[MentionCandidate]:
    """搜索可插入对话的卷/章节 mention 候选项。"""
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")

    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    clamped_limit = max(1, min(limit, 50))
    matched_volumes = await volume_repo.search_by_project(
        session,
        project_id,
        normalized_query,
        limit=clamped_limit,
    )
    matched_chapters = await chapter_repo.search_with_volume_by_project(
        session,
        project_id,
        normalized_query,
        limit=clamped_limit,
    )

    scored_candidates: list[tuple[int, int, MentionCandidate]] = []

    for index, volume in enumerate(matched_volumes):
        title = _display_volume_title(volume)
        scored_candidates.append(
            (
                _match_rank(title, normalized_query),
                index,
                MentionCandidate(
                    kind="volume",
                    id=volume.id,
                    title=title,
                    label=title,
                ),
            )
        )

    base_index = len(scored_candidates)
    for offset, (chapter, volume) in enumerate(matched_chapters):
        chapter_title = _display_chapter_title(chapter)
        volume_title = _display_volume_title(volume)
        chapter_rank = _match_rank(chapter_title, normalized_query)
        volume_rank = _match_rank(volume_title, normalized_query)
        scored_candidates.append(
            (
                min(chapter_rank, volume_rank + 3),
                base_index + offset,
                MentionCandidate(
                    kind="chapter",
                    id=chapter.id,
                    title=chapter_title,
                    label=chapter_title,
                    description=volume_title,
                ),
            )
        )

    scored_candidates.sort(
        key=lambda item: (
            item[0],
            0 if item[2].kind == "volume" else 1,
            item[1],
        )
    )
    return [candidate for _, _, candidate in scored_candidates[:clamped_limit]]


@dataclass
class ChapterSearchMatch:
    """章节内容搜索匹配行。"""

    line_number: int
    line_text: str


@dataclass
class ChapterSearchResult:
    """章节内容搜索结果。"""

    chapter_id: str
    chapter_title: str
    volume_title: str
    matches: list[ChapterSearchMatch]


@dataclass
class ChapterSearchResponse:
    """章节内容搜索响应。"""

    results: list[ChapterSearchResult]
    total_chapters: int
    total_matches: int


async def search_chapters(
    session: AsyncSession,
    project_id: str,
    query: str,
) -> ChapterSearchResponse:
    """按内容搜索章节。"""
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")

    if not query.strip():
        return ChapterSearchResponse(results=[], total_chapters=0, total_matches=0)

    entries = await chapter_repo.search_by_content(session, project_id, query)

    results: list[ChapterSearchResult] = []
    total_matches = 0
    lower_query = query.lower()

    for chapter, volume in entries:
        lines = chapter.content.split("\n")
        matches: list[ChapterSearchMatch] = []
        for line_number, line in enumerate(lines, start=1):
            if lower_query in line.lower():
                matches.append(
                    ChapterSearchMatch(
                        line_number=line_number,
                        line_text=line,
                    )
                )

        if matches:
            results.append(
                ChapterSearchResult(
                    chapter_id=chapter.id,
                    chapter_title=_display_chapter_title(chapter),
                    volume_title=_display_volume_title(volume),
                    matches=matches,
                )
            )
            total_matches += len(matches)

    return ChapterSearchResponse(
        results=results,
        total_chapters=len(results),
        total_matches=total_matches,
    )


async def update_chapter(
    session: AsyncSession,
    chapter_id: str,
    title: str | None = None,
    content: str | None = None,
    word_count: int | None = None,
    synopsis: str | None = None,
    writing_status: str | None = None,
    word_count_target: int | None | object = UNSET,
) -> Chapter:
    """
    更新章节。

    Args:
        session: 数据库 session。
        chapter_id: 章节 ID。
        title: 新标题，可选。
        content: 新内容，可选。
        word_count: 字数（前端计算），如果为 None 则后端计算。
        synopsis: 作者梗概，可选。只在传入时更新。
        writing_status: 写作状态，可选。只在传入时更新。
        word_count_target: 本章目标字数。UNSET 表示不改，None 表示清空。

    Returns:
        更新后的章节实例。

    Raises:
        NotFoundError: 章节不存在。
    """
    chapter = await get_chapter(session, chapter_id)
    old_word_count = chapter.word_count
    old_content = chapter.content
    old_title = chapter.title

    title_changed = False
    if title is not None and title != chapter.title:
        chapter.title = title
        title_changed = True

    content_changed = False
    if content is not None and content != chapter.content:
        validate_editor_content(content)
        chapter.content = content
        # 优先使用前端传递的字数，否则后端计算
        chapter.word_count = (
            word_count if word_count is not None else _count_words(content)
        )
        content_changed = True
    elif word_count is not None and word_count != chapter.word_count:
        # 如果只传了 word_count 没传 content，也只在字数实际变化时更新
        chapter.word_count = word_count
        content_changed = True

    plan_changed = False
    if synopsis is not None:
        normalized_synopsis = normalize_synopsis(synopsis)
        if normalized_synopsis != chapter.synopsis:
            chapter.synopsis = normalized_synopsis
            plan_changed = True
    if writing_status is not None:
        normalized_status = normalize_writing_status(writing_status)
        if normalized_status != chapter.writing_status:
            chapter.writing_status = normalized_status
            plan_changed = True

    target_changed = False
    if word_count_target is not UNSET:
        normalized_target = normalize_word_count_target(
            word_count_target if isinstance(word_count_target, int) else None
        )
        if normalized_target != chapter.word_count_target:
            chapter.word_count_target = normalized_target
            target_changed = True

    if title_changed or content_changed or plan_changed or target_changed:
        chapter.updated_at = datetime.now(UTC)
    chapter = await chapter_repo.update_chapter(session, chapter)

    # 如果有任何变化，更新项目统计（包括 updated_at）
    if title_changed or content_changed:
        if content_changed:
            await writing_activity_service.record_activity(
                session,
                project_id=chapter.project_id,
                chapter_id=chapter.id,
                chapter_title=chapter.title,
                source="user",
                operation="update",
                old_word_count=old_word_count,
                new_word_count=chapter.word_count,
            )
        await _update_project_stats(session, chapter.project_id)
    if content is not None and content != old_content:
        # 手动修订钩子：按定值节流（距最近一条 manual 修订 ≥10 分钟或字数变化
        # ≥200）把本次内容变化记入 revisions/commits 版本时间线。版本记录是
        # 保险层而非主路径，钩子失败只记日志，不阻断保存。
        try:
            await manual_revision_service.maybe_create_manual_revision(
                session,
                chapter=chapter,
                old_title=old_title,
                old_content=old_content,
                old_word_count=old_word_count,
            )
        except Exception:
            logger.exception(f"记录手动修订失败（不影响保存）: chapter_id={chapter_id}")

        from app.retrieval.chapter_index import (
            ChapterIndexIntegrationService,
            safe_maybe_enqueue_auto_index,
        )
        from app.retrieval.index_status import schedule_emit_index_status

        await ChapterIndexIntegrationService().mark_chapter_stale_if_changed(
            session,
            chapter,
        )
        await safe_maybe_enqueue_auto_index(session, project_id=chapter.project_id)
        schedule_emit_index_status(session, chapter.project_id)
    return chapter


async def delete_chapter(
    session: AsyncSession,
    chapter_id: str,
    *,
    record_activity: bool = True,
    activity_source: writing_activity_service.WritingActivitySource = "user",
    revision_id: str | None = None,
    task_id: str | None = None,
    agent_session_id: str | None = None,
) -> None:
    """
    删除章节。

    Args:
        session: 数据库 session。
        chapter_id: 章节 ID。

    Raises:
        NotFoundError: 章节不存在。
    """
    chapter = await get_chapter(session, chapter_id)
    project_id = chapter.project_id
    volume_id = chapter.volume_id
    deleted_volume_order = chapter.order
    chapters = await chapter_repo.list_metadata_by_project(session, project_id)
    volumes = await volume_repo.list_by_project(session, project_id)
    deleted_global_order = global_order_index(chapters, volumes)[chapter_id]
    old_title = chapter.title
    old_word_count = chapter.word_count

    from app.retrieval.chapter_index import ChapterIndexIntegrationService

    await ChapterIndexIntegrationService().delete_chapter_index(session, chapter)

    from app.retrieval.index_status import schedule_emit_index_status

    schedule_emit_index_status(session, project_id)

    await chapter_summary_repo.delete_by_chapter_id(session, chapter_id)
    long_term_summaries = (
        await chapter_summary_repo.list_long_term_summaries_by_project(
            session, project_id
        )
    )
    affected_ranges = list(
        {
            (summary.start_order, summary.end_order)
            for summary in long_term_summaries
            if summary.start_order is not None
            and summary.end_order is not None
            and summary.end_order >= deleted_global_order
        }
    )
    if affected_ranges:
        await chapter_summary_repo.delete_long_term_summaries_by_ranges(
            session, project_id, affected_ranges
        )

    await plot_beat_repo.delete_by_chapter_ids(session, [chapter_id])
    await margin_note_repo.delete_by_chapter_ids(session, [chapter_id])

    # 删除章节
    await chapter_repo.delete(session, chapter)

    if record_activity:
        await writing_activity_service.record_activity(
            session,
            project_id=project_id,
            chapter_id=chapter_id,
            chapter_title=old_title,
            source=activity_source,
            operation="delete",
            old_word_count=old_word_count,
            new_word_count=0,
            revision_id=revision_id,
            task_id=task_id,
            agent_session_id=agent_session_id,
        )

    # 调整后续章节的顺序
    max_order = await chapter_repo.get_max_order(session, volume_id)
    if deleted_volume_order <= max_order:
        # 将所有 order > deleted_volume_order 的章节 order 减 1
        await chapter_repo.shift_orders(
            session, volume_id, deleted_volume_order + 1, max_order, -1
        )

    # 更新项目统计
    await _update_volume_stats(session, volume_id)
    await _update_project_stats(session, project_id)


async def delete_chapters_in_volume(session: AsyncSession, volume_id: str) -> None:
    """批量删除卷内章节，避免逐章重复扫描项目和重算统计。"""
    chapters = await chapter_repo.list_by_volume(session, volume_id)
    if not chapters:
        return

    project_id = chapters[0].project_id
    project_chapters = await chapter_repo.list_metadata_by_project(session, project_id)
    volumes = await volume_repo.list_by_project(session, project_id)
    global_orders = global_order_index(project_chapters, volumes)
    deleted_global_orders = [
        global_orders[chapter.id] for chapter in chapters if chapter.id in global_orders
    ]

    from app.retrieval.chapter_index import ChapterIndexIntegrationService
    from app.retrieval.index_status import schedule_emit_index_status

    index_service = ChapterIndexIntegrationService()
    for chapter in chapters:
        await index_service.delete_chapter_index(session, chapter)
    schedule_emit_index_status(session, project_id)

    await chapter_summary_repo.delete_by_chapter_ids(
        session, [chapter.id for chapter in chapters]
    )
    if deleted_global_orders:
        long_term_summaries = (
            await chapter_summary_repo.list_long_term_summaries_by_project(
                session, project_id
            )
        )
        first_deleted_order = min(deleted_global_orders)
        affected_ranges = [
            (summary.start_order, summary.end_order)
            for summary in long_term_summaries
            if summary.start_order is not None
            and summary.end_order is not None
            and summary.end_order >= first_deleted_order
        ]
        await chapter_summary_repo.delete_long_term_summaries_by_ranges(
            session, project_id, affected_ranges
        )

    await plot_beat_repo.delete_by_chapter_ids(
        session, [chapter.id for chapter in chapters]
    )
    await margin_note_repo.delete_by_chapter_ids(
        session, [chapter.id for chapter in chapters]
    )
    await chapter_repo.delete_by_volume(session, volume_id)
    for chapter in chapters:
        await writing_activity_service.record_activity(
            session,
            project_id=project_id,
            chapter_id=chapter.id,
            chapter_title=chapter.title,
            source="user",
            operation="delete",
            old_word_count=chapter.word_count,
            new_word_count=0,
        )
    await _update_project_stats(session, project_id)


async def reorder_chapters(
    session: AsyncSession,
    volume_id: str,
    chapter_ids: list[str],
) -> list[Chapter]:
    """
    批量重排章节顺序。

    Args:
        session: 数据库 session。
        volume_id: 卷 ID。
        chapter_ids: 按新顺序排列的章节 ID 列表。

    Returns:
        更新后的章节列表。

    Raises:
        NotFoundError: 章节不存在或不属于指定卷。
        ValueError: 章节数量不匹配。
    """
    chapters = await chapter_repo.get_metadata_by_ids(session, chapter_ids)
    chapter_map = {c.id: c for c in chapters}

    if len(chapters) != len(chapter_ids):
        missing = [cid for cid in chapter_ids if cid not in chapter_map]
        raise NotFoundError(f"章节不存在: {missing}")

    for chapter in chapters:
        if chapter.volume_id != volume_id:
            raise ValueError(f"章节 {chapter.id} 不属于卷 {volume_id}")

    orders = {
        chapter_id: new_order
        for new_order, chapter_id in enumerate(chapter_ids, start=1)
        if chapter_map[chapter_id].order != new_order
    }

    updated_at = await chapter_repo.update_orders(session, orders)
    if updated_at is not None:
        for chapter_id, chapter_order in orders.items():
            chapter = chapter_map[chapter_id]
            set_committed_value(chapter, "order", chapter_order)
            set_committed_value(chapter, "updated_at", updated_at)

    updated_chapters = chapters
    order_lookup = {cid: idx for idx, cid in enumerate(chapter_ids)}
    updated_chapters.sort(key=lambda c: order_lookup.get(c.id, 0))
    return updated_chapters


async def merge_chapters(
    session: AsyncSession,
    chapter_ids: list[str],
    *,
    title: str | None = None,
    separator: str = "\n\n",
) -> Chapter:
    """
    合并同一卷内的多个章节。

    按阅读顺序把各章正文接在一起，第一章为目标章，其余章删除。
    旁注和情节节拍随正文归到目标章；目标章已有同一条线的节拍时丢弃重复。

    Args:
        session: 数据库 session。
        chapter_ids: 要合并的章节 ID，至少两个。
        title: 合并后的标题，缺省沿用第一章标题。
        separator: 各章正文之间的分隔文本。

    Returns:
        合并后的目标章。

    Raises:
        NotFoundError: 有章节不存在。
        ValueError: 不足两章、跨卷跨项目，或合并后超出编辑器内容上限。
    """
    if len(chapter_ids) < 2:
        raise ValueError("至少选择两章才能合并")

    chapters = await chapter_repo.get_by_ids(session, chapter_ids)
    by_id = {chapter.id: chapter for chapter in chapters}
    missing = [chapter_id for chapter_id in chapter_ids if chapter_id not in by_id]
    if missing:
        raise NotFoundError(f"章节不存在: {missing}")

    ordered = sorted((by_id[chapter_id] for chapter_id in chapter_ids), key=lambda c: c.order)
    project_ids = {chapter.project_id for chapter in ordered}
    volume_ids = {chapter.volume_id for chapter in ordered}
    if len(project_ids) != 1:
        raise ValueError("只能合并同一项目下的章节")
    if len(volume_ids) != 1:
        raise ValueError("只能合并同一卷下的章节")

    target = ordered[0]
    merged_content = separator.join(
        chapter.content for chapter in ordered if chapter.content
    )
    validate_editor_content(merged_content)

    # 梗概按行合并，去掉重复行，超出上限就只保留目标章的梗概。
    merged_synopsis = "\n".join(
        dict.fromkeys(
            line
            for chapter in ordered
            for line in chapter.synopsis.splitlines()
            if line.strip()
        )
    )
    if len(merged_synopsis) > SYNOPSIS_MAX_LENGTH:
        merged_synopsis = target.synopsis

    final_title = title.strip() if title else target.title
    merged_word_count = _count_words(merged_content)
    updated_target = await update_chapter(
        session,
        target.id,
        title=final_title,
        content=merged_content,
        word_count=merged_word_count,
        synopsis=merged_synopsis,
    )

    # 合并前把旁注和节拍先挪到目标章，避免随后删除时一并清掉。
    now = datetime.now(UTC)
    for chapter in ordered[1:]:
        for note in await margin_note_repo.list_by_chapter(session, chapter.id):
            note.chapter_id = target.id
            note.updated_at = now
            await margin_note_repo.save(session, note)

    target_thread_ids = {
        beat.thread_id
        for beat in await plot_beat_repo.list_by_chapter(session, target.id)
    }
    for chapter in ordered[1:]:
        for beat in await plot_beat_repo.list_by_chapter(session, chapter.id):
            if beat.thread_id in target_thread_ids:
                await plot_beat_repo.delete(session, beat)
                continue
            beat.chapter_id = target.id
            beat.updated_at = now
            await plot_beat_repo.save(session, beat)
            target_thread_ids.add(beat.thread_id)

    for chapter in ordered[1:]:
        await delete_chapter(session, chapter.id)

    logger.info(
        f"合并章节: {chapter_ids} -> {target.id}, 合并后 {merged_word_count} 字"
    )
    return updated_target


async def split_chapter(
    session: AsyncSession,
    chapter_id: str,
    split_line: int,
    *,
    title: str | None = None,
) -> tuple[Chapter, Chapter]:
    """
    从指定行把一章拆成两章。

    该行之前留在原章，从该行起划入紧跟其后的新章。新章沿用原章标题加「（续）」
    和写作状态，不继承目标字数。锚点落在新章里的旁注跟着挪过去。

    Args:
        session: 数据库 session。
        chapter_id: 要拆分的章节 ID。
        split_line: 拆分行号（1 基，含该行），必须落在第 2 行到最后一行之间。
        title: 新章标题，缺省在原标题后加「（续）」。

    Returns:
        (留在原处的前半章, 划出去的新章)。

    Raises:
        NotFoundError: 章节不存在。
        ValueError: 行号越界或拆分导致某一半为空。
    """
    target = await get_chapter(session, chapter_id)
    lines = target.content.split("\n")
    if len(lines) < 2:
        raise ValueError("这一章还没有可以拆开的分界行")
    if split_line > len(lines):
        raise ValueError(f"拆分行号不能超过本章行数 {len(lines)}")

    above = "\n".join(lines[: split_line - 1])
    below = "\n".join(lines[split_line - 1 :])
    if not above.strip():
        raise ValueError("拆分点太靠前，前半章会变成空章")
    if not below.strip():
        raise ValueError("拆分点太靠后，新章会变成空章")

    updated_target = await update_chapter(
        session,
        target.id,
        content=above,
        word_count=_count_words(above),
    )

    new_title = title if title else f"{_display_chapter_title(target)}（续）"
    new_chapter = await create_chapter(
        session,
        project_id=target.project_id,
        volume_id=target.volume_id,
        title=new_title[:200],
        content=below,
        writing_status=target.writing_status,
    )

    # 新章默认落在卷末，把它挪到紧跟目标章的位置：
    # 目标章之后（含新章在内）整体后移一位，再把新章放进空出来的位置。
    target_order = updated_target.order
    if new_chapter.order != target_order + 1:
        max_order = await chapter_repo.get_max_order(session, target.volume_id)
        await chapter_repo.shift_orders(
            session,
            target.volume_id,
            target_order + 1,
            max_order,
            +1,
        )
        new_chapter.order = target_order + 1
        new_chapter.updated_at = datetime.now(UTC)
        new_chapter = await chapter_repo.update_chapter(session, new_chapter)

    # 锚点只在新章正文里出现的旁注跟着挪过去；两边都出现的留原章。
    now = datetime.now(UTC)
    for note in await margin_note_repo.list_by_chapter(session, target.id):
        anchor = note.anchor_text
        if anchor and anchor in below and anchor not in above:
            note.chapter_id = new_chapter.id
            note.updated_at = now
            await margin_note_repo.save(session, note)

    # 正文已经对半分了，原章摘要作废。
    await chapter_summary_repo.delete_by_chapter_id(session, target.id)

    logger.info(
        f"拆分章节: {target.id} @ 第 {split_line} 行 -> 新章 {new_chapter.id}"
    )
    return updated_target, new_chapter


async def move_chapter_to_volume(
    session: AsyncSession,
    chapter_id: str,
    volume_id: str,
    *,
    record_activity: bool = True,
    activity_source: writing_activity_service.WritingActivitySource = "user",
    revision_id: str | None = None,
    task_id: str | None = None,
    agent_session_id: str | None = None,
) -> Chapter:
    """跨卷移动章节，追加到目标卷末尾。"""
    chapter = await get_chapter(session, chapter_id)
    source_volume_id = chapter.volume_id
    if source_volume_id == volume_id:
        return chapter

    target_volume = await volume_repo.get_by_id(session, volume_id)
    if target_volume is None or target_volume.project_id != chapter.project_id:
        raise NotFoundError(f"卷不存在: {volume_id}")

    old_order = chapter.order
    chapter.order = 0
    await chapter_repo.update_chapter(session, chapter)

    source_max_order = await chapter_repo.get_max_order(session, source_volume_id)
    if old_order <= source_max_order:
        await chapter_repo.shift_orders(
            session, source_volume_id, old_order + 1, source_max_order, -1
        )

    target_max_order = await chapter_repo.get_max_order(session, volume_id)
    chapter.volume_id = volume_id
    chapter.order = target_max_order + 1
    chapter.updated_at = datetime.now(UTC)
    chapter = await chapter_repo.update_chapter(session, chapter)

    await _update_volume_stats(session, source_volume_id)
    await _update_volume_stats(session, volume_id)
    await _update_project_stats(session, chapter.project_id)
    from app.retrieval.chapter_index import (
        ChapterIndexIntegrationService,
        safe_maybe_enqueue_auto_index,
    )
    from app.retrieval.index_status import schedule_emit_index_status

    await ChapterIndexIntegrationService().mark_chapter_stale_if_indexed(
        session,
        chapter,
    )
    await safe_maybe_enqueue_auto_index(session, project_id=chapter.project_id)
    schedule_emit_index_status(session, chapter.project_id)
    if record_activity:
        await writing_activity_service.record_activity(
            session,
            project_id=chapter.project_id,
            chapter_id=chapter.id,
            chapter_title=chapter.title,
            source=activity_source,
            operation="move_to_volume",
            old_word_count=chapter.word_count,
            new_word_count=chapter.word_count,
            revision_id=revision_id,
            task_id=task_id,
            agent_session_id=agent_session_id,
        )
    return chapter

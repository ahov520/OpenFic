# -*- coding: utf-8 -*-
"""
WorldInfo Entry Service - 世界书条目业务逻辑层。
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.editor_content_limits import validate_editor_content
from app.core.errors import NotFoundError
from app.core.utils.tiktoken import get_encoding
from app.storage.models.world_info_entry import WorldInfoEntry
from app.storage.repos import world_info_entry_repo
from app.storage.services.world_info_service import get_world_info
from app.tavern.keywords import dump_keywords
from app.tavern.parse import parse_worldbook_bytes


class WorldInfoEntryNameConflictError(ValueError):
    """世界书条目名称冲突。"""


@dataclass
class WorldInfoImportEntry:
    """归一化后的世界书导入条目。"""

    uid: int
    name: str
    content: str
    is_enabled: bool
    order: int
    keywords: list[str] = field(default_factory=list)
    is_constant: bool = True
    source: str = ""


@dataclass
class WorldInfoImportPreviewResult:
    """世界书导入预览结果。"""

    entries: list[WorldInfoImportEntry]


@dataclass
class WorldInfoImportResult:
    """世界书导入结果。"""

    world_info_id: str
    imported_count: int


@dataclass
class WorldInfoEntrySearchMatch:
    """搜索匹配项。"""

    line_number: int
    line_text: str


@dataclass
class WorldInfoEntrySearchResult:
    """单个条目的搜索结果。"""

    entry_id: str
    entry_name: str
    uid: int
    matches: list[WorldInfoEntrySearchMatch]


@dataclass
class WorldInfoEntrySearchResponse:
    """搜索响应。"""

    results: list[WorldInfoEntrySearchResult]
    total_entries: int
    total_matches: int


def _calculate_token_count(content: str) -> int:
    """计算条目内容的 token 数。"""
    try:
        return len(get_encoding("cl100k_base").encode(content))
    except Exception:
        return len(content) // 4


async def _get_existing_entry_names(
    session: AsyncSession,
    world_info_id: str,
    exclude_entry_id: str | None = None,
) -> set[str]:
    entries = await world_info_entry_repo.list_all_by_world_info(session, world_info_id)
    return {entry.name for entry in entries if entry.id != exclude_entry_id}


def generate_unique_entry_name(base_name: str, existing_names: set[str]) -> str:
    normalized_name = base_name.strip()
    if normalized_name not in existing_names:
        return normalized_name

    counter = 1
    while f"{normalized_name} ({counter})" in existing_names:
        counter += 1
    return f"{normalized_name} ({counter})"


async def ensure_entry_name_available(
    session: AsyncSession,
    world_info_id: str,
    name: str,
    exclude_entry_id: str | None = None,
) -> str:
    normalized_name = name.strip()
    existing_names = await _get_existing_entry_names(
        session, world_info_id, exclude_entry_id=exclude_entry_id
    )
    if normalized_name in existing_names:
        raise WorldInfoEntryNameConflictError(f"世界书条目名称已存在: {normalized_name}")
    return normalized_name


def parse_sillytavern_worldbook(raw_payload: bytes) -> WorldInfoImportPreviewResult:
    """解析 SillyTavern 世界书 JSON 并归一化为当前项目结构。"""
    drafts = parse_worldbook_bytes(raw_payload)
    return WorldInfoImportPreviewResult(
        entries=[
            WorldInfoImportEntry(
                uid=draft.uid,
                name=draft.name,
                content=draft.content,
                is_enabled=draft.is_enabled,
                order=draft.order,
                keywords=draft.keywords,
                is_constant=draft.is_constant,
                source=draft.source,
            )
            for draft in drafts
        ]
    )


async def import_entries(
    session: AsyncSession,
    world_info_id: str,
    entries: list[WorldInfoImportEntry],
    mode: str = "append",
) -> WorldInfoImportResult:
    """批量导入世界书条目。"""
    await get_world_info(session, world_info_id)

    if mode not in {"append", "overwrite"}:
        raise ValueError(f"不支持的导入模式: {mode}")

    for entry in entries:
        validate_editor_content(entry.content)

    if mode == "overwrite":
        await world_info_entry_repo.delete_by_world_info(session, world_info_id)
        existing_entries: list[WorldInfoEntry] = []
    else:
        existing_entries = await world_info_entry_repo.list_all_by_world_info(session, world_info_id)

    existing_by_name = {entry.name: entry for entry in existing_entries}
    max_uid = await world_info_entry_repo.get_max_uid(session, world_info_id)
    max_order = await world_info_entry_repo.get_max_order(session, world_info_id)

    imported_count = 0
    for entry in entries:
        token_count = _calculate_token_count(entry.content)
        existing = existing_by_name.get(entry.name)
        if existing is not None:
            existing.content = entry.content
            existing.token_count = token_count
            existing.is_enabled = entry.is_enabled
            existing.keywords_json = dump_keywords(entry.keywords)
            existing.is_constant = entry.is_constant
            existing.source = entry.source
            existing.updated_at = datetime.now(UTC)
            await world_info_entry_repo.update_entry(session, existing)
            imported_count += 1
            continue

        max_uid += 1
        max_order += 1
        created = await world_info_entry_repo.create(
            session,
            WorldInfoEntry(
                world_info_id=world_info_id,
                uid=max_uid,
                name=entry.name,
                order=max_order,
                content=entry.content,
                token_count=token_count,
                is_enabled=entry.is_enabled,
                keywords_json=dump_keywords(entry.keywords),
                is_constant=entry.is_constant,
                source=entry.source,
            ),
        )
        existing_by_name[created.name] = created
        imported_count += 1

    return WorldInfoImportResult(
        world_info_id=world_info_id,
        imported_count=imported_count,
    )


# ============== 世界书条目操作 ==============


async def create_entry(
    session: AsyncSession,
    world_info_id: str,
    name: str,
    content: str = "",
    token_count: int = 0,
    is_enabled: bool = True,
    keywords: list[str] | None = None,
    is_constant: bool = True,
) -> WorldInfoEntry:
    """
    创建世界书条目。

    Args:
        session: 数据库 session。
        world_info_id: 世界书 ID。
        name: 条目名称。
        content: 条目内容。
        token_count: Token 数量。
        is_enabled: 开关状态。

    Returns:
        创建的条目实例。

    Raises:
        NotFoundError: 世界书不存在。
    """
    validate_editor_content(content)

    # 检查世界书是否存在
    await get_world_info(session, world_info_id)

    existing_names = await _get_existing_entry_names(session, world_info_id)
    unique_name = generate_unique_entry_name(name, existing_names)

    # 获取当前最大 UID 和 order
    max_uid = await world_info_entry_repo.get_max_uid(session, world_info_id)
    max_order = await world_info_entry_repo.get_max_order(session, world_info_id)

    entry = WorldInfoEntry(
        world_info_id=world_info_id,
        uid=max_uid + 1,
        name=unique_name,
        order=max_order + 1,
        content=content,
        token_count=token_count,
        is_enabled=is_enabled,
        keywords_json=dump_keywords(keywords),
        is_constant=is_constant,
    )
    return await world_info_entry_repo.create(session, entry)


async def get_entry(session: AsyncSession, entry_id: str) -> WorldInfoEntry:
    """
    获取世界书条目。

    Args:
        session: 数据库 session。
        entry_id: 条目 ID。

    Returns:
        条目实例。

    Raises:
        NotFoundError: 条目不存在。
    """
    entry = await world_info_entry_repo.get_by_id(session, entry_id)
    if entry is None:
        raise NotFoundError(f"条目不存在: {entry_id}")
    return entry


async def list_entries(
    session: AsyncSession,
    world_info_id: str,
) -> list[WorldInfoEntry]:
    """
    获取世界书条目列表。

    Args:
        session: 数据库 session。
        world_info_id: 世界书 ID。
    Returns:
        条目列表。

    Raises:
        NotFoundError: 世界书不存在。
    """
    # 检查世界书是否存在
    await get_world_info(session, world_info_id)

    return await world_info_entry_repo.list_all_by_world_info(session, world_info_id)


async def update_entry(
    session: AsyncSession,
    entry_id: str,
    name: str | None = None,
    content: str | None = None,
    token_count: int | None = None,
    is_enabled: bool | None = None,
    keywords: list[str] | None = None,
    is_constant: bool | None = None,
) -> WorldInfoEntry:
    """
    更新世界书条目。

    Args:
        session: 数据库 session。
        entry_id: 条目 ID。
        name: 新名称。
        content: 新内容。
        token_count: 新 Token 数量。
        is_enabled: 新开关状态。

    Returns:
        更新后的条目实例。

    Raises:
        NotFoundError: 条目不存在。
    """
    entry = await get_entry(session, entry_id)

    if name is not None:
        entry.name = await ensure_entry_name_available(
            session,
            entry.world_info_id,
            name,
            exclude_entry_id=entry.id,
        )
    if content is not None:
        validate_editor_content(content)
        entry.content = content
    if token_count is not None:
        entry.token_count = token_count
    if is_enabled is not None:
        entry.is_enabled = is_enabled
    if keywords is not None:
        entry.keywords_json = dump_keywords(keywords)
    if is_constant is not None:
        entry.is_constant = is_constant

    entry.updated_at = datetime.now(UTC)
    return await world_info_entry_repo.update_entry(session, entry)


async def delete_all_entries(session: AsyncSession, world_info_id: str) -> int:
    """
    删除世界书的所有条目。

    Args:
        session: 数据库 session。
        world_info_id: 世界书 ID。

    Returns:
        删除的条目数量。
    """
    await get_world_info(session, world_info_id)
    entries = await world_info_entry_repo.list_all_by_world_info(session, world_info_id)
    count = len(entries)
    await world_info_entry_repo.delete_by_world_info(session, world_info_id)
    return count


async def delete_entry(session: AsyncSession, entry_id: str) -> None:
    """
    删除世界书条目，并调整后续条目的 order。

    Args:
        session: 数据库 session。
        entry_id: 条目 ID。

    Raises:
        NotFoundError: 条目不存在。
    """
    entry = await get_entry(session, entry_id)
    old_order = entry.order
    world_info_id = entry.world_info_id

    # 删除条目
    await world_info_entry_repo.delete(session, entry)

    # 将后续条目的 order 减 1
    max_order = await world_info_entry_repo.get_max_order(session, world_info_id)
    if old_order < max_order:
        await world_info_entry_repo.shift_orders(
            session, world_info_id, old_order + 1, max_order, -1
        )


async def move_entry(
    session: AsyncSession,
    entry_id: str,
    new_order: int,
) -> WorldInfoEntry:
    """
    移动世界书条目到新位置。

    Args:
        session: 数据库 session。
        entry_id: 条目 ID。
        new_order: 新排序位置。

    Returns:
        更新后的条目实例。

    Raises:
        NotFoundError: 条目不存在。
        ValueError: 新位置无效。
    """
    entry = await get_entry(session, entry_id)
    old_order = entry.order
    world_info_id = entry.world_info_id

    if new_order < 1:
        raise ValueError("排序位置必须大于 0")

    max_order = await world_info_entry_repo.get_max_order(session, world_info_id)
    if new_order > max_order:
        new_order = max_order

    if old_order == new_order:
        return entry

    # 调整其他条目的 order
    if new_order < old_order:
        # 向前移动：[new_order, old_order) 的条目 order +1
        await world_info_entry_repo.shift_orders(
            session, world_info_id, new_order, old_order - 1, 1
        )
    else:
        # 向后移动：(old_order, new_order] 的条目 order -1
        await world_info_entry_repo.shift_orders(
            session, world_info_id, old_order + 1, new_order, -1
        )

    entry.order = new_order
    entry.updated_at = datetime.now(UTC)
    return await world_info_entry_repo.update_entry(session, entry)


async def toggle_entry(session: AsyncSession, entry_id: str) -> WorldInfoEntry:
    """
    切换世界书条目的开关状态。

    Args:
        session: 数据库 session。
        entry_id: 条目 ID。

    Returns:
        更新后的条目实例。

    Raises:
        NotFoundError: 条目不存在。
    """
    entry = await get_entry(session, entry_id)
    entry.is_enabled = not entry.is_enabled
    entry.updated_at = datetime.now(UTC)
    return await world_info_entry_repo.update_entry(session, entry)


async def batch_toggle_entries(
    session: AsyncSession,
    world_info_id: str,
    entry_ids: list[str],
    is_enabled: bool,
) -> int:
    """批量切换条目启用状态。"""
    await get_world_info(session, world_info_id)
    updated = await world_info_entry_repo.batch_toggle(
        session, world_info_id, entry_ids, is_enabled
    )
    return updated


async def batch_delete_entries(
    session: AsyncSession,
    world_info_id: str,
    entry_ids: list[str],
) -> int:
    """批量删除条目。"""
    await get_world_info(session, world_info_id)
    deleted = await world_info_entry_repo.batch_delete(
        session, world_info_id, entry_ids
    )
    return deleted


async def search_entries(
    session: AsyncSession,
    world_info_id: str,
    query: str,
) -> WorldInfoEntrySearchResponse:
    await get_world_info(session, world_info_id)

    if not query.strip():
        return WorldInfoEntrySearchResponse(results=[], total_entries=0, total_matches=0)

    entries = await world_info_entry_repo.search_by_content(
        session, world_info_id, query
    )

    results: list[WorldInfoEntrySearchResult] = []
    total_matches = 0
    lower_query = query.lower()

    for entry in entries:
        lines = entry.content.split("\n")
        matches: list[WorldInfoEntrySearchMatch] = []
        for line_number, line in enumerate(lines, start=1):
            if lower_query in line.lower():
                matches.append(
                    WorldInfoEntrySearchMatch(
                        line_number=line_number,
                        line_text=line,
                    )
                )

        if matches:
            results.append(
                WorldInfoEntrySearchResult(
                    entry_id=entry.id,
                    entry_name=entry.name,
                    uid=entry.uid,
                    matches=matches,
                )
            )
            total_matches += len(matches)

    return WorldInfoEntrySearchResponse(
        results=results,
        total_entries=len(results),
        total_matches=total_matches,
    )

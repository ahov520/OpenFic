"""Import SillyTavern cards, world books, and presets into a writing project."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import save_character_image_bytes
from app.storage.repos import agent_rule_repo, character_repo, skill_repo
from app.storage.services import (
    agent_rule_service,
    character_service,
    skill_service,
    world_info_entry_service,
    world_info_service,
)
from app.tavern.parse import (
    CharacterCardDraft,
    LoreEntryDraft,
    PresetBlock,
    PresetDraft,
    detect_material_kind,
    parse_character_card_bytes,
    parse_preset_bytes,
    parse_worldbook_bytes,
)


@dataclass
class TavernPreview:
    """Preview shown before writing tavern materials."""

    kind: str
    character_name: str = ""
    description_preview: str = ""
    discarded: list[str] = field(default_factory=list)
    lore_entries: list[LoreEntryDraft] = field(default_factory=list)
    preset_name: str = ""
    blocks: list[PresetBlock] = field(default_factory=list)


@dataclass
class TavernImportResult:
    """Counts written by a confirmed import."""

    kind: str
    character_id: str | None = None
    imported_entries: int = 0
    imported_rules: int = 0
    imported_skills: int = 0


def preview_material(
    raw: bytes,
    *,
    filename: str,
    user_name: str = "",
) -> TavernPreview:
    """Parse a file without writing it."""
    kind = detect_material_kind(raw, filename)
    if kind == "preset":
        preset = parse_preset_bytes(raw, user_name=user_name)
        return TavernPreview(kind="preset", preset_name=preset.name, blocks=preset.blocks)
    if kind == "character_card":
        card = parse_character_card_bytes(raw, filename=filename, user_name=user_name)
        return _preview_from_card(card)
    entries = parse_worldbook_bytes(raw)
    return TavernPreview(kind="worldbook", lore_entries=entries)


async def import_material(
    session: AsyncSession,
    *,
    project_id: str,
    raw: bytes,
    filename: str,
    user_name: str = "",
    mode: str = "append",
    included_block_ids: set[str] | None = None,
) -> TavernImportResult:
    """Write a confirmed tavern file into the project."""
    kind = detect_material_kind(raw, filename)
    if kind == "preset":
        preset = parse_preset_bytes(raw, user_name=user_name)
        rules, skills = await _import_preset(session, project_id, preset, included_block_ids)
        return TavernImportResult(kind="preset", imported_rules=rules, imported_skills=skills)
    if kind == "character_card":
        card = parse_character_card_bytes(raw, filename=filename, user_name=user_name)
        return await _import_card(
            session,
            project_id=project_id,
            card=card,
            raw=raw,
            filename=filename,
            mode=mode,
            included_block_ids=included_block_ids,
        )
    entries = parse_worldbook_bytes(raw)
    imported = await _import_lore(session, project_id, entries, mode)
    return TavernImportResult(kind="worldbook", imported_entries=imported)


def _preview_from_card(card: CharacterCardDraft) -> TavernPreview:
    return TavernPreview(
        kind="character_card",
        character_name=card.name,
        description_preview=card.description[:400],
        discarded=card.discarded,
        lore_entries=card.lore_entries,
        blocks=card.style_blocks,
    )


async def _import_card(
    session: AsyncSession,
    *,
    project_id: str,
    card: CharacterCardDraft,
    raw: bytes,
    filename: str,
    mode: str,
    included_block_ids: set[str] | None,
) -> TavernImportResult:
    character = await character_service.create_character(
        session,
        project_id,
        card.name,
        card.description,
    )
    if filename.lower().endswith(".png") or raw.startswith(b"\x89PNG"):
        character.image_path = save_character_image_bytes(character.id, raw)
        character.updated_at = datetime.now(UTC)
        character = await character_repo.update(session, character)
    imported_entries = await _import_lore(session, project_id, card.lore_entries, mode)
    origin_key = f"tavern-card:{project_id}:{card.name}"
    imported_rules, _imported_skills = await _write_blocks(
        session,
        project_id=project_id,
        preset_name=card.name,
        origin_key=origin_key,
        blocks=card.style_blocks,
        included_block_ids=included_block_ids,
    )
    return TavernImportResult(
        kind="character_card",
        character_id=character.id,
        imported_entries=imported_entries,
        imported_rules=imported_rules,
        imported_skills=_imported_skills,
    )


async def _import_lore(
    session: AsyncSession,
    project_id: str,
    entries: list[LoreEntryDraft],
    mode: str,
) -> int:
    if not entries:
        return 0
    world_info = await world_info_service.get_or_create_world_info_by_project(session, project_id)
    imported = await world_info_entry_service.import_entries(
        session,
        world_info.id,
        [
            world_info_entry_service.WorldInfoImportEntry(
                uid=entry.uid,
                name=entry.name,
                content=entry.content,
                is_enabled=entry.is_enabled,
                order=entry.order,
                keywords=entry.keywords,
                is_constant=entry.is_constant,
                source=entry.source,
            )
            for entry in entries
        ],
        mode=mode,
    )
    return imported.imported_count


async def _import_preset(
    session: AsyncSession,
    project_id: str,
    preset: PresetDraft,
    included_block_ids: set[str] | None,
) -> tuple[int, int]:
    origin_key = f"tavern-preset:{project_id}:{preset.name}"
    return await _write_blocks(
        session,
        project_id=project_id,
        preset_name=preset.name,
        origin_key=origin_key,
        blocks=preset.blocks,
        included_block_ids=included_block_ids,
    )


async def _write_blocks(
    session: AsyncSession,
    *,
    project_id: str,
    preset_name: str,
    origin_key: str,
    blocks: list[PresetBlock],
    included_block_ids: set[str] | None,
    replace_existing: bool = True,
) -> tuple[int, int]:
    if replace_existing:
        await agent_rule_repo.delete_by_origin_key(session, project_id, origin_key)
        await skill_repo.delete_by_origin_key(session, origin_key)
    rule_count = 0
    skill_count = 0
    for block in blocks:
        if not _block_included(block, included_block_ids):
            continue
        if block.bucket == "rule":
            await agent_rule_service.create_rule(
                session,
                title=f"{preset_name} / {block.name}"[:200],
                content=block.content,
                scope="project",
                project_id=project_id,
                origin_key=origin_key,
            )
            rule_count += 1
        elif block.bucket == "skill":
            summary = block.content.replace("\n", " ")[:120]
            await skill_service.create_skill(
                session,
                name=f"{preset_name} / {block.name}"[:200],
                summary=summary,
                content=block.content,
                is_enabled=False,
                origin_key=origin_key,
            )
            skill_count += 1
    return rule_count, skill_count


def _block_included(block: PresetBlock, included_block_ids: set[str] | None) -> bool:
    if block.bucket == "discarded":
        return False
    if included_block_ids is None:
        return True
    return block.block_id in included_block_ids

"""整项目备份：后台任务打包 zip，导入时还原为全新项目。

zip 结构（白名单，共 14 个文件）：
- meta.json：项目元数据与各类实体计数
- 13 个实体 JSON：卷、章、章梗概（chapter/long_term 两种各一文件）、旁注、
  情节线、节拍、角色、世界书、世界书条目、笔记分类、笔记、Agent 定义

红线：settings、llm_audit_log、模型凭据等不属于这 14 个文件，永不导出。
导入语义是「还原为全新项目」：全部实体重新生成 id，外键按旧→新映射重建，
agent_definitions 全局表按唯一 key upsert；绝不覆盖或删除已有项目。
还原内嵌 id 的字段时同步重算派生值：long_term 摘要的
source_chapter_summary_signatures_json（签名含 chapter_id，必须按新 id 重算），
chapter.plan_check_payload gaps[].thread_id（缺口簿记按键对齐）。
已知限制：还原目前在 HTTP 请求内同步执行，超大项目可能撞客户端超时。
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.persistence.model import AgentDefinitionRecord
from app.background.jobs import service as background_service
from app.background.jobs.models import BackgroundJob
from app.background.jobs.states import (
    JOB_STATUS_CANCEL_REQUESTED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
)
from app.chapter_export.service import sanitize_filename_segment
from app.core.ids import generate_id
from app.memory.chapter.summary_service import chapter_summary_signature
from app.settings import settings
from app.storage.models.character import Character
from app.storage.models.chapter import Chapter
from app.storage.models.chapter_summary import ChapterSummary
from app.storage.models.margin_note import ChapterMarginNote
from app.storage.models.note import Note, NoteCategory
from app.storage.models.plot_thread import PlotBeat, PlotThread
from app.storage.models.project import Project
from app.storage.models.volume import Volume
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry
from app.storage.repos import (
    agent_definition_repo,
    chapter_repo,
    chapter_summary_repo,
    character_repo,
    margin_note_repo,
    note_category_repo,
    note_repo,
    plot_beat_repo,
    plot_thread_repo,
    project_repo,
    volume_repo,
    world_info_entry_repo,
    world_info_repo,
)


BACKUP_JOB_TYPE = "project_backup"
BACKUP_FILE_PREFIX = "project-backup-"
BACKUP_FILE_TTL = timedelta(hours=24)
BACKUP_KIND = "openfic-project-backup"
BACKUP_SCHEMA_VERSION = 1
BACKUP_UPLOAD_MAX_BYTES = 1 << 30
# zip 解压后的总字节上限，防压缩炸弹。
BACKUP_UNCOMPRESSED_MAX_BYTES = 2 << 30

META_FILE_NAME = "meta.json"

# 13 个实体文件；「章梗概」按 summary_type 拆成 chapter 与 long_term 两份。
ENTITY_FILE_NAMES: dict[str, str] = {
    "volumes": "volumes.json",
    "chapters": "chapters.json",
    "chapter_summaries": "chapter_summaries.json",
    "long_term_summaries": "long_term_summaries.json",
    "margin_notes": "margin_notes.json",
    "plot_threads": "plot_threads.json",
    "plot_beats": "plot_beats.json",
    "characters": "characters.json",
    "world_info": "world_info.json",
    "world_info_entries": "world_info_entries.json",
    "note_categories": "note_categories.json",
    "notes": "notes.json",
    "agent_definitions": "agent_definitions.json",
}

BACKUP_WHITELIST_FILE_NAMES = frozenset({META_FILE_NAME, *ENTITY_FILE_NAMES.values()})


class ProjectBackupError(ValueError):
    """备份文件无效或数据不完整。"""


def ensure_project_backups_dir() -> Path:
    """确保备份成品目录存在。"""
    settings.project_backups_dir.mkdir(parents=True, exist_ok=True)
    return settings.project_backups_dir


def backup_file_paths(job_id: str) -> tuple[Path, Path]:
    """返回任务的临时文件与成品 zip 路径。"""
    directory = ensure_project_backups_dir()
    basename = f"{BACKUP_FILE_PREFIX}{job_id}"
    return directory / f"{basename}.part", directory / f"{basename}.zip"


async def create_backup_plan(
    session: AsyncSession,
    *,
    project_id: str,
    local_date: str,
) -> dict[str, object]:
    """校验项目存在并生成备份任务 payload。"""
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise LookupError(f"项目不存在: {project_id}")
    title = sanitize_filename_segment(project.title, "未命名项目")
    return {
        "project_id": project_id,
        "filename": f"{title}-项目备份-{local_date}.zip",
    }


async def collect_project_backup(
    session: AsyncSession, project_id: str
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """经 repo 层读取项目全部实体，产出 meta 与各实体 JSON 行。"""
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise LookupError(f"项目不存在: {project_id}")

    volumes = await volume_repo.list_by_project(session, project_id)
    chapters = await chapter_repo.list_by_project(session, project_id)
    chapter_summaries = await chapter_summary_repo.list_chapter_summaries_by_project(
        session, project_id
    )
    long_term_summaries = await chapter_summary_repo.list_long_term_summaries_by_project(
        session, project_id
    )
    margin_notes = await margin_note_repo.list_by_project(session, project_id)
    plot_threads = await plot_thread_repo.list_by_project(session, project_id)
    plot_beats = await plot_beat_repo.list_by_project(session, project_id)
    characters = await character_repo.list_all_by_project(session, project_id)
    world_info = await world_info_repo.get_by_project_id(session, project_id)
    world_info_entries = (
        await world_info_entry_repo.list_all_by_world_info(session, world_info.id)
        if world_info is not None
        else []
    )
    note_categories = await note_category_repo.list_by_project(session, project_id)
    notes = await note_repo.list_by_project(session, project_id)
    agent_definitions = await agent_definition_repo.list_all(session)

    entities: dict[str, list[dict[str, Any]]] = {
        "volumes": [row.model_dump(mode="json") for row in volumes],
        "chapters": [row.model_dump(mode="json") for row in chapters],
        "chapter_summaries": [row.model_dump(mode="json") for row in chapter_summaries],
        "long_term_summaries": [
            row.model_dump(mode="json") for row in long_term_summaries
        ],
        "margin_notes": [row.model_dump(mode="json") for row in margin_notes],
        "plot_threads": [row.model_dump(mode="json") for row in plot_threads],
        "plot_beats": [row.model_dump(mode="json") for row in plot_beats],
        "characters": [row.model_dump(mode="json") for row in characters],
        "world_info": (
            [world_info.model_dump(mode="json")] if world_info is not None else []
        ),
        "world_info_entries": [
            row.model_dump(mode="json") for row in world_info_entries
        ],
        "note_categories": [row.model_dump(mode="json") for row in note_categories],
        "notes": [row.model_dump(mode="json") for row in notes],
        "agent_definitions": [
            row.model_dump(mode="json") for row in agent_definitions
        ],
    }

    counts = {key: len(rows) for key, rows in entities.items()}
    meta: dict[str, Any] = {
        "kind": BACKUP_KIND,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "project": {
            "title": project.title,
            "description": project.description,
            "word_count": project.word_count,
            "chapter_count": project.chapter_count,
            "cover_path": project.cover_path,
        },
        "counts": counts,
    }
    return meta, entities


async def write_project_backup(context) -> dict[str, object]:
    """收集全部实体并写入任务专属 zip 文件。"""
    payload = background_service.parse_json_object(context.job.payload_json)
    project_id = payload.get("project_id")
    filename = payload.get("filename")
    if not isinstance(project_id, str) or not isinstance(filename, str):
        raise ProjectBackupError("备份任务参数无效")

    part_path, output_path = backup_file_paths(context.job_id)
    try:
        await context.check_cancelled()
        meta, entities = await collect_project_backup(context.session, project_id)
        counts = {key: len(rows) for key, rows in entities.items()}

        context.job = await background_service.update_progress(
            context.session,
            context.publisher,
            context.job,
            current=1,
            total=2,
            message="writing",
            extra_payload={"stage": "writing"},
        )
        await context.commit()

        files = {META_FILE_NAME: json.dumps(meta, ensure_ascii=False, indent=2)}
        for key, rows in entities.items():
            files[ENTITY_FILE_NAMES[key]] = json.dumps(rows, ensure_ascii=False)

        await context.check_cancelled()
        await asyncio.to_thread(_write_backup_zip, part_path, files)
        await context.check_cancelled()
        await asyncio.to_thread(os.replace, part_path, output_path)

        expires_at = datetime.now(UTC) + BACKUP_FILE_TTL
        return {
            "filename": filename,
            "expires_at": expires_at.isoformat(),
            "counts": counts,
        }
    except BaseException:
        await _delete_backup_files(context.job_id)
        raise


def get_backup_summary(job: BackgroundJob) -> dict[str, object]:
    """从后台任务记录抽取前端状态所需的备份摘要。"""
    payload = background_service.parse_json_object(job.payload_json)
    progress = background_service.parse_json_object(job.progress_json)
    result = background_service.parse_json_object(job.result_json)
    error = background_service.parse_json_object(job.error_json)
    expires_at = _parse_datetime(result.get("expires_at"))
    counts_raw = result.get("counts")
    counts = (
        {
            key: int(value)
            for key, value in counts_raw.items()
            if isinstance(value, (int, float))
        }
        if isinstance(counts_raw, dict)
        else {}
    )
    total_value = progress.get("total")
    return {
        "id": job.id,
        "status": job.status,
        "filename": payload.get("filename", "项目备份.zip"),
        "counts": counts,
        "current": int(progress.get("current", 0)),
        "total": int(total_value) if isinstance(total_value, int) else 0,
        "stage": progress.get("stage") if isinstance(progress.get("stage"), str) else None,
        "expires_at": expires_at,
        "error_message": error.get("message") if isinstance(error.get("message"), str) else None,
    }


def is_backup_download_available(job: BackgroundJob) -> bool:
    """检查任务成品 zip 是否在下载有效期内。"""
    if job.type != BACKUP_JOB_TYPE or job.status != JOB_STATUS_SUCCEEDED:
        return False
    expires_at = _parse_datetime(
        background_service.parse_json_object(job.result_json).get("expires_at")
    )
    if expires_at is None or expires_at <= datetime.now(UTC):
        return False
    _part_path, output_path = backup_file_paths(job.id)
    return output_path.is_file()


@dataclass(frozen=True)
class ParsedProjectBackup:
    """解析后的备份内容：meta 与各实体 JSON 行。"""

    meta: dict[str, Any]
    entities: dict[str, list[dict[str, Any]]]

    @property
    def counts(self) -> dict[str, int]:
        return {key: len(rows) for key, rows in self.entities.items()}

    @property
    def total_entities(self) -> int:
        return sum(self.counts.values())

    @property
    def project_title(self) -> str:
        project = self.meta.get("project")
        if isinstance(project, dict) and isinstance(project.get("title"), str):
            return project["title"]
        return "未命名项目"


def parse_backup_archive(data: bytes) -> ParsedProjectBackup:
    """解析上传的备份 zip。只读取白名单文件，其余条目忽略以兼容后续扩展。"""
    if not data:
        raise ProjectBackupError("备份文件为空")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            uncompressed_total = sum(info.file_size for info in bundle.infolist())
            if uncompressed_total > BACKUP_UNCOMPRESSED_MAX_BYTES:
                raise ProjectBackupError("备份文件解压后过大，已拒绝导入")
            names = set(bundle.namelist())
            if META_FILE_NAME not in names:
                raise ProjectBackupError("备份缺少 meta.json，不是 OpenFic 项目备份")
            meta = _load_json_entry(bundle, META_FILE_NAME, expected_list=False)
            if not isinstance(meta, dict):
                raise ProjectBackupError("meta.json 必须是 JSON 对象")
            if meta.get("kind") != BACKUP_KIND:
                raise ProjectBackupError("备份文件类型不符，不是 OpenFic 项目备份")
            schema_version = meta.get("schema_version")
            if not isinstance(schema_version, int) or schema_version > BACKUP_SCHEMA_VERSION:
                raise ProjectBackupError("备份版本过新，请升级应用后再导入")
            entities = {
                key: _load_entity_rows(bundle, key)
                for key in ENTITY_FILE_NAMES
            }
    except zipfile.BadZipFile as exc:
        raise ProjectBackupError("备份文件不是有效的 zip 压缩包") from exc

    # meta.counts 与实际内容必须一致，被截断的备份不允许静默导入成空壳。
    meta_counts = meta.get("counts")
    if isinstance(meta_counts, dict):
        expected = {
            key: int(value)
            for key, value in meta_counts.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        if expected != {key: len(rows) for key, rows in entities.items()}:
            raise ProjectBackupError("备份清单计数与实际内容不一致，文件可能被截断或损坏")
    return ParsedProjectBackup(meta=meta, entities=entities)


async def restore_project(
    session: AsyncSession, parsed: ParsedProjectBackup
) -> tuple[Project, dict[str, int]]:
    """把备份还原为全新项目：全部实体重新生成 id，外键按旧→新映射重建。"""
    meta_project = parsed.meta.get("project")
    if not isinstance(meta_project, dict):
        raise ProjectBackupError("备份 meta.json 缺少 project 信息")

    project = Project(
        title=_meta_str(meta_project, "title", "未命名项目"),
        description=_meta_optional_str(meta_project, "description"),
        word_count=_meta_int(meta_project, "word_count"),
        chapter_count=_meta_int(meta_project, "chapter_count"),
        cover_path=_restore_cover_path(meta_project.get("cover_path")),
    )
    await project_repo.create(session, project)

    volume_map = await _restore_volumes(session, parsed.entities["volumes"], project.id)
    # 先还原情节线：章节的 plan_check_payload 内嵌 thread_id，需要映射。
    thread_map = await _restore_plot_threads(
        session, parsed.entities["plot_threads"], project.id
    )
    chapter_map = await _restore_chapters(
        session, parsed.entities["chapters"], project.id, volume_map, thread_map
    )
    # 章梗概先落库，long_term 的源签名要按还原后的行重算。
    chapter_summary_map = await _restore_chapter_summaries(
        session, parsed.entities["chapter_summaries"], project.id, chapter_map, volume_map
    )
    await _restore_long_term_summaries(
        session,
        parsed.entities["long_term_summaries"],
        project.id,
        chapter_map,
        volume_map,
        chapter_summary_map,
    )
    await _restore_margin_notes(
        session, parsed.entities["margin_notes"], project.id, chapter_map
    )
    await _restore_plot_beats(
        session, parsed.entities["plot_beats"], project.id, thread_map, chapter_map
    )
    await _restore_characters(session, parsed.entities["characters"], project.id)
    world_info_map = await _restore_world_info(
        session, parsed.entities["world_info"], project.id
    )
    await _restore_world_info_entries(
        session, parsed.entities["world_info_entries"], world_info_map
    )
    category_map = await _restore_note_categories(
        session, parsed.entities["note_categories"], project.id
    )
    await _restore_notes(session, parsed.entities["notes"], project.id, category_map)
    await _restore_agent_definitions(session, parsed.entities["agent_definitions"])
    return project, parsed.counts


async def _restore_volumes(
    session: AsyncSession, rows: list[dict[str, Any]], new_project_id: str
) -> dict[str, str]:
    id_map: dict[str, str] = {}
    for row in rows:
        volume = _build_row(Volume, row, ENTITY_FILE_NAMES["volumes"])
        old_id = volume.id
        volume.id = generate_id()
        volume.project_id = new_project_id
        await volume_repo.create(session, volume)
        id_map[old_id] = volume.id
    return id_map


async def _restore_chapters(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    new_project_id: str,
    volume_map: dict[str, str],
    thread_map: dict[str, str],
) -> dict[str, str]:
    id_map: dict[str, str] = {}
    for row in rows:
        chapter = _build_row(Chapter, row, ENTITY_FILE_NAMES["chapters"])
        if chapter.volume_id not in volume_map:
            raise ProjectBackupError("备份数据引用了不存在的卷，无法还原")
        old_id = chapter.id
        chapter.id = generate_id()
        chapter.project_id = new_project_id
        chapter.volume_id = volume_map[chapter.volume_id]
        # plan_check_payload 的 gaps[].thread_id 内嵌旧情节线 id，按映射替换，
        # 否则还原后缺口簿记全部被误判为「计划已变化」。
        chapter.plan_check_payload = _remap_plan_check_payload(
            chapter.plan_check_payload, thread_map
        )
        await chapter_repo.create(session, chapter)
        id_map[old_id] = chapter.id
    return id_map


async def _restore_chapter_summaries(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    new_project_id: str,
    chapter_map: dict[str, str],
    volume_map: dict[str, str],
) -> dict[str, ChapterSummary]:
    """还原 chapter 型摘要，返回 新章节 id → 还原后的摘要行。"""
    by_new_chapter_id: dict[str, ChapterSummary] = {}
    for row in rows:
        summary = _build_row(ChapterSummary, row, ENTITY_FILE_NAMES["chapter_summaries"])
        if summary.chapter_id is not None and summary.chapter_id not in chapter_map:
            raise ProjectBackupError("备份数据引用了不存在的章节，无法还原")
        if summary.volume_id is not None and summary.volume_id not in volume_map:
            raise ProjectBackupError("备份数据引用了不存在的卷，无法还原")
        summary.id = generate_id()
        summary.project_id = new_project_id
        summary.chapter_id = (
            chapter_map[summary.chapter_id] if summary.chapter_id is not None else None
        )
        summary.volume_id = (
            volume_map[summary.volume_id] if summary.volume_id is not None else None
        )
        # job_id 指向旧库的后台任务，还原后不再有意义。
        summary.job_id = None
        # source_chapter_ids_json 是 JSON 字符串内嵌的旧章节 id 数组，须解析替换。
        summary.source_chapter_ids_json = _remap_id_list_json(
            summary.source_chapter_ids_json, chapter_map, "chapter_summaries.json"
        )
        await chapter_summary_repo.create(session, summary)
        if summary.summary_type == "chapter" and summary.chapter_id is not None:
            by_new_chapter_id[summary.chapter_id] = summary
    return by_new_chapter_id


async def _restore_long_term_summaries(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    new_project_id: str,
    chapter_map: dict[str, str],
    volume_map: dict[str, str],
    chapter_summary_map: dict[str, ChapterSummary],
) -> None:
    """还原 long_term 型摘要，并按新章节 id 重算源签名。

    chapter_summary_signature 把 chapter_id 混入哈希，旧签名在还原后必然失配，
    会让长程摘要被永久误判 stale 而反复重跑 LLM。
    """
    for row in rows:
        summary = _build_row(
            ChapterSummary, row, ENTITY_FILE_NAMES["long_term_summaries"]
        )
        if summary.chapter_id is not None and summary.chapter_id not in chapter_map:
            raise ProjectBackupError("备份数据引用了不存在的章节，无法还原")
        if summary.volume_id is not None and summary.volume_id not in volume_map:
            raise ProjectBackupError("备份数据引用了不存在的卷，无法还原")
        summary.id = generate_id()
        summary.project_id = new_project_id
        summary.chapter_id = (
            chapter_map[summary.chapter_id] if summary.chapter_id is not None else None
        )
        summary.volume_id = (
            volume_map[summary.volume_id] if summary.volume_id is not None else None
        )
        summary.job_id = None
        source_ids_json = _remap_id_list_json(
            summary.source_chapter_ids_json, chapter_map, "long_term_summaries.json"
        )
        summary.source_chapter_ids_json = source_ids_json
        # 与 summary_service 的窗口签名规则一致：按 chapter_order 排序后逐条签名。
        source_ids = json.loads(source_ids_json)
        source_rows = sorted(
            (
                chapter_summary_map[chapter_id]
                for chapter_id in source_ids
                if chapter_id in chapter_summary_map
            ),
            key=lambda item: item.chapter_order or 0,
        )
        summary.source_chapter_summary_signatures_json = json.dumps(
            [chapter_summary_signature(item) for item in source_rows],
            ensure_ascii=False,
        )
        await chapter_summary_repo.create(session, summary)


async def _restore_margin_notes(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    new_project_id: str,
    chapter_map: dict[str, str],
) -> None:
    for row in rows:
        note = _build_row(ChapterMarginNote, row, ENTITY_FILE_NAMES["margin_notes"])
        if note.chapter_id not in chapter_map:
            raise ProjectBackupError("备份数据引用了不存在的章节，无法还原")
        note.id = generate_id()
        note.project_id = new_project_id
        note.chapter_id = chapter_map[note.chapter_id]
        await margin_note_repo.create(session, note)


async def _restore_plot_threads(
    session: AsyncSession, rows: list[dict[str, Any]], new_project_id: str
) -> dict[str, str]:
    id_map: dict[str, str] = {}
    for row in rows:
        thread = _build_row(PlotThread, row, ENTITY_FILE_NAMES["plot_threads"])
        old_id = thread.id
        thread.id = generate_id()
        thread.project_id = new_project_id
        await plot_thread_repo.create(session, thread)
        id_map[old_id] = thread.id
    return id_map


async def _restore_plot_beats(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    new_project_id: str,
    thread_map: dict[str, str],
    chapter_map: dict[str, str],
) -> None:
    for row in rows:
        beat = _build_row(PlotBeat, row, ENTITY_FILE_NAMES["plot_beats"])
        if beat.thread_id not in thread_map or beat.chapter_id not in chapter_map:
            raise ProjectBackupError("备份数据引用了不存在的情节线或章节，无法还原")
        beat.id = generate_id()
        beat.project_id = new_project_id
        beat.thread_id = thread_map[beat.thread_id]
        beat.chapter_id = chapter_map[beat.chapter_id]
        await plot_beat_repo.create(session, beat)


async def _restore_characters(
    session: AsyncSession, rows: list[dict[str, Any]], new_project_id: str
) -> None:
    for row in rows:
        character = _build_row(Character, row, ENTITY_FILE_NAMES["characters"])
        character.id = generate_id()
        character.project_id = new_project_id
        await character_repo.create(session, character)


async def _restore_world_info(
    session: AsyncSession, rows: list[dict[str, Any]], new_project_id: str
) -> dict[str, str]:
    id_map: dict[str, str] = {}
    for row in rows:
        info = _build_row(WorldInfo, row, ENTITY_FILE_NAMES["world_info"])
        old_id = info.id
        info.id = generate_id()
        info.project_id = new_project_id
        await world_info_repo.create(session, info)
        id_map[old_id] = info.id
    return id_map


async def _restore_world_info_entries(
    session: AsyncSession, rows: list[dict[str, Any]], world_info_map: dict[str, str]
) -> None:
    for row in rows:
        entry = _build_row(WorldInfoEntry, row, ENTITY_FILE_NAMES["world_info_entries"])
        if entry.world_info_id not in world_info_map:
            raise ProjectBackupError("备份数据引用了不存在的世界书，无法还原")
        entry.id = generate_id()
        entry.world_info_id = world_info_map[entry.world_info_id]
        await world_info_entry_repo.create(session, entry)


async def _restore_note_categories(
    session: AsyncSession, rows: list[dict[str, Any]], new_project_id: str
) -> dict[str, str]:
    file_name = ENTITY_FILE_NAMES["note_categories"]
    id_map: dict[str, str] = {}
    created: list[tuple[dict[str, Any], NoteCategory]] = []
    for row in rows:
        category = _build_row(NoteCategory, row, file_name)
        old_id = category.id
        # parent_id 自引用，先全部落库，再按映射补父子关系。
        category.id = generate_id()
        category.project_id = new_project_id
        category.parent_id = None
        await note_category_repo.create(session, category)
        id_map[old_id] = category.id
        created.append((row, category))
    for row, category in created:
        old_parent_id = row.get("parent_id")
        if isinstance(old_parent_id, str) and old_parent_id:
            if old_parent_id not in id_map:
                raise ProjectBackupError("备份数据引用了不存在的笔记分类，无法还原")
            category.parent_id = id_map[old_parent_id]
    await session.flush()
    return id_map


async def _restore_notes(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    new_project_id: str,
    category_map: dict[str, str],
) -> None:
    for row in rows:
        note = _build_row(Note, row, ENTITY_FILE_NAMES["notes"])
        if note.category_id is not None and note.category_id not in category_map:
            raise ProjectBackupError("备份数据引用了不存在的笔记分类，无法还原")
        note.id = generate_id()
        note.project_id = new_project_id
        note.category_id = (
            category_map[note.category_id] if note.category_id is not None else None
        )
        await note_repo.create(session, note)


async def _restore_agent_definitions(
    session: AsyncSession, rows: list[dict[str, Any]]
) -> None:
    """agent_definitions 是全局表：按唯一 key upsert，不新建重复行。"""
    for row in rows:
        incoming = _build_row(AgentDefinitionRecord, row, ENTITY_FILE_NAMES["agent_definitions"])
        existing = await agent_definition_repo.get_by_key(session, incoming.key)
        if existing is None:
            incoming.id = generate_id()
            await agent_definition_repo.create(session, incoming)
            continue
        existing.display_name = incoming.display_name
        existing.description = incoming.description
        existing.kind = incoming.kind
        existing.prompt_agent_name = incoming.prompt_agent_name
        existing.model_id = incoming.model_id
        existing.enabled_tool_categories = incoming.enabled_tool_categories
        existing.enabled_skills = incoming.enabled_skills
        existing.metadata_json = incoming.metadata_json
        existing.enabled = incoming.enabled
        existing.order_index = incoming.order_index
        existing.source = incoming.source
        existing.color = incoming.color
        existing.icon = incoming.icon
        existing.delegatable_agents = incoming.delegatable_agents
        existing.updated_at = datetime.now(UTC)
        await agent_definition_repo.update(session, existing)


def _write_backup_zip(path: Path, files: dict[str, str]) -> None:
    """把白名单文件打包成 zip（在.to_thread 中执行）。"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in sorted(files):
            bundle.writestr(name, files[name])


async def _delete_backup_files(job_id: str) -> None:
    part_path, output_path = backup_file_paths(job_id)
    await asyncio.to_thread(part_path.unlink, missing_ok=True)
    await asyncio.to_thread(output_path.unlink, missing_ok=True)


async def cleanup_project_backup_files(session: AsyncSession) -> int:
    """清除过期或已不可达的整项目备份 zip（与章节导出清理同型）。"""
    directory = ensure_project_backups_dir()
    removed = 0
    now = datetime.now(UTC)
    paths = await asyncio.to_thread(lambda: list(directory.iterdir()))
    for path in paths:
        job_id = _job_id_from_backup_path(path)
        if job_id is None:
            continue
        job = await background_service.get_job(session, job_id)
        should_keep = False
        if job is not None and job.type == BACKUP_JOB_TYPE:
            if path.suffix == ".part":
                should_keep = job.status in {
                    JOB_STATUS_PENDING,
                    JOB_STATUS_RUNNING,
                    JOB_STATUS_CANCEL_REQUESTED,
                }
            elif path.suffix == ".zip" and job.status == JOB_STATUS_SUCCEEDED:
                expires_at = _parse_datetime(
                    background_service.parse_json_object(job.result_json).get("expires_at")
                )
                should_keep = expires_at is not None and expires_at > now
        if should_keep:
            continue
        await asyncio.to_thread(path.unlink, missing_ok=True)
        removed += 1
    return removed


def _job_id_from_backup_path(path: Path) -> str | None:
    if path.suffix not in {".part", ".zip"} or not path.name.startswith(BACKUP_FILE_PREFIX):
        return None
    job_id = path.name[len(BACKUP_FILE_PREFIX) : -len(path.suffix)]
    return job_id or None


def _build_row(model_cls, row: dict[str, Any], file_name: str):
    try:
        return model_cls.model_validate(row)
    except ValidationError as exc:
        raise ProjectBackupError(f"备份文件 {file_name} 中存在无效数据: {exc}") from exc


def _remap_id_list_json(raw: str, id_map: dict[str, str], field_name: str) -> str:
    """解析 JSON 字符串内嵌的 id 数组，按旧→新映射替换。

    与其余外键同一口径：引用了备份中不存在的 id 视为备份损坏，直接报错。
    """
    try:
        values = json.loads(raw) if raw else []
    except json.JSONDecodeError as exc:
        raise ProjectBackupError(f"{field_name} 不是有效的 JSON 数组，无法还原") from exc
    if not isinstance(values, list):
        raise ProjectBackupError(f"{field_name} 必须是 JSON 数组，无法还原")
    remapped = []
    for value in values:
        if not isinstance(value, str) or value not in id_map:
            raise ProjectBackupError(
                f"{field_name} 引用了备份中不存在的章节，无法还原"
            )
        remapped.append(id_map[value])
    return json.dumps(remapped, ensure_ascii=False)


def _remap_plan_check_payload(
    raw: str | None, thread_map: dict[str, str]
) -> str | None:
    """把 plan_check_payload 里 gaps[].thread_id 换成新情节线 id。"""
    if not raw:
        return raw
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(payload, dict):
        return raw
    changed = False
    for section in ("gaps", "unchecked"):
        items = payload.get(section)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            old_thread_id = item.get("thread_id")
            if isinstance(old_thread_id, str) and old_thread_id in thread_map:
                item["thread_id"] = thread_map[old_thread_id]
                changed = True
    if not changed:
        return raw
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _restore_cover_path(value: object) -> str | None:
    """封面文件留在本机磁盘（covers_dir 相对路径）；文件仍在才保留，否则置空。"""
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    if not (settings.covers_dir / candidate).is_file():
        return None
    return value


def _load_json_entry(bundle: zipfile.ZipFile, name: str, *, expected_list: bool) -> Any:
    try:
        raw = json.loads(bundle.read(name).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProjectBackupError(f"备份文件 {name} 不是有效的 JSON") from exc
    if expected_list and not isinstance(raw, list):
        raise ProjectBackupError(f"备份文件 {name} 必须是 JSON 数组")
    return raw


def _load_entity_rows(bundle: zipfile.ZipFile, key: str) -> list[dict[str, Any]]:
    filename = ENTITY_FILE_NAMES[key]
    if filename not in bundle.namelist():
        return []
    rows = _load_json_entry(bundle, filename, expected_list=True)
    return [row for row in rows if isinstance(row, dict)]


def _meta_str(meta: dict[str, Any], key: str, default: str) -> str:
    value = meta.get(key)
    return value if isinstance(value, str) and value else default


def _meta_optional_str(meta: dict[str, Any], key: str) -> str | None:
    value = meta.get(key)
    return value if isinstance(value, str) else None


def _meta_int(meta: dict[str, Any], key: str) -> int:
    value = meta.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

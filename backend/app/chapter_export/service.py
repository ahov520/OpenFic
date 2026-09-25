"""章节 TXT 导出任务的选择、文件写入和清理逻辑。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import re
from typing import Any, Iterable

import aiofiles
from sqlalchemy.ext.asyncio import AsyncSession

from app.background.jobs import service as background_service
from app.background.jobs.models import BackgroundJob
from app.background.jobs.states import (
    JOB_STATUS_CANCEL_REQUESTED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
)
from app.chapter_export.docx_writer import write_docx
from app.chapter_export.epub_writer import write_epub
from app.chapter_export.formats import (
    DEFAULT_EXPORT_FORMAT,
    EXPORT_FILE_SUFFIXES,
    PART_SUFFIX,
    ExportDocumentChapter,
    ExportDocumentSpec,
    ExportDocumentVolume,
    export_suffix,
    normalize_export_format,
)
from app.settings import settings
from app.storage.repos import chapter_repo, project_repo, volume_repo


EXPORT_JOB_TYPE = "chapter_export"
EXPORT_FILE_PREFIX = "chapter-export-"
EXPORT_FILE_TTL = timedelta(hours=24)
EXPORT_BATCH_SIZE = 20


class ChapterExportSelectionError(ValueError):
    """导出选择无效。"""


@dataclass(frozen=True)
class ExportChapter:
    """任务中固化的章节元数据，不包含正文。"""

    id: str
    volume_id: str
    title: str
    word_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "volume_id": self.volume_id,
            "title": self.title,
            "word_count": self.word_count,
        }


@dataclass(frozen=True)
class ExportVolume:
    """整卷 TXT 标题与归属章节。"""

    id: str
    title: str
    order: int
    chapter_ids: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "order": self.order,
            "chapter_ids": self.chapter_ids,
        }


@dataclass(frozen=True)
class ChapterExportPlan:
    """创建后台任务前解析出的固定导出范围。"""

    project_id: str
    filename: str
    mode: str
    format: str = DEFAULT_EXPORT_FORMAT
    book_title: str = ""
    author: str = ""
    chapters: list[ExportChapter] = field(default_factory=list)
    volumes: list[ExportVolume] = field(default_factory=list)

    @property
    def chapter_ids(self) -> list[str]:
        return [chapter.id for chapter in self.chapters]

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)

    @property
    def word_count(self) -> int:
        return sum(chapter.word_count for chapter in self.chapters)

    @property
    def volume_count(self) -> int:
        return len(self.volumes) if self.mode == "volumes" else len({chapter.volume_id for chapter in self.chapters})

    def to_payload(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "filename": self.filename,
            "mode": self.mode,
            "format": self.format,
            "book_title": self.book_title,
            "author": self.author,
            "chapters": [chapter.to_dict() for chapter in self.chapters],
            "volumes": [volume.to_dict() for volume in self.volumes],
            "chapter_count": self.chapter_count,
            "word_count": self.word_count,
            "volume_count": self.volume_count,
        }


def ensure_chapter_exports_dir() -> Path:
    """确保导出成品目录存在。"""
    settings.chapter_exports_dir.mkdir(parents=True, exist_ok=True)
    return settings.chapter_exports_dir


def export_file_paths(job_id: str, export_format: str = DEFAULT_EXPORT_FORMAT) -> tuple[Path, Path]:
    """返回任务的临时文件与成品文件路径（成品后缀由导出格式决定）。"""
    directory = ensure_chapter_exports_dir()
    basename = f"{EXPORT_FILE_PREFIX}{job_id}"
    suffix = export_suffix(normalize_export_format(export_format))
    return directory / f"{basename}{PART_SUFFIX}", directory / f"{basename}{suffix}"


def sanitize_filename_segment(value: str, fallback: str) -> str:
    """将项目和卷名转换为跨平台安全的文件名片段。"""
    normalized = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", " ", value).strip().strip(".")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized[:120] or fallback


def chinese_number(value: int) -> str:
    """将正整数转换为卷标题使用的简体中文数字。"""
    if value <= 0:
        return str(value)

    numerals = "零一二三四五六七八九"
    units = ("", "十", "百", "千")
    group_units = ("", "万", "亿", "兆")

    def format_group(group: int) -> str:
        parts: list[str] = []
        zero_pending = False
        for exponent in range(3, -1, -1):
            digit = (group // (10**exponent)) % 10
            if digit:
                if zero_pending:
                    parts.append("零")
                    zero_pending = False
                parts.append(f"{numerals[digit]}{units[exponent]}")
            elif parts:
                zero_pending = True
        return "".join(parts)

    groups: list[int] = []
    remaining = value
    while remaining:
        groups.append(remaining % 10000)
        remaining //= 10000

    result = ""
    zero_pending = False
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if not group:
            zero_pending = bool(result)
            continue
        if zero_pending or (result and group < 1000):
            result += "零"
        result += f"{format_group(group)}{group_units[index]}"
        zero_pending = False
    if 10 <= value < 20:
        return f"十{result.removeprefix('一十')}"
    return result


async def create_export_plan(
    session: AsyncSession,
    *,
    project_id: str,
    selected_volume_ids: Iterable[str],
    included_chapter_ids: Iterable[str],
    excluded_chapter_ids: Iterable[str],
    local_date: str,
    export_format: str = DEFAULT_EXPORT_FORMAT,
) -> ChapterExportPlan:
    """校验选择并固定导出范围、顺序、格式和文件名。"""
    try:
        normalized_format = normalize_export_format(export_format)
    except ValueError as exc:
        raise ChapterExportSelectionError(str(exc)) from exc

    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise LookupError(f"项目不存在: {project_id}")

    volumes = await volume_repo.list_by_project(session, project_id)
    chapter_metadata = await chapter_repo.list_export_metadata_by_project(session, project_id)
    volume_by_id = {volume.id: volume for volume in volumes}
    chapter_by_id = {
        chapter_id: (volume_id, title, word_count)
        for chapter_id, volume_id, title, word_count in chapter_metadata
    }

    selected_volumes = set(selected_volume_ids)
    included_chapters = set(included_chapter_ids)
    excluded_chapters = set(excluded_chapter_ids)

    unknown_volumes = selected_volumes.difference(volume_by_id)
    unknown_chapters = included_chapters.union(excluded_chapters).difference(chapter_by_id)
    if unknown_volumes or unknown_chapters:
        raise ChapterExportSelectionError("导出选择包含不属于当前项目的卷或章节")

    selected_ids = {
        chapter_id
        for chapter_id, (volume_id, _title, _word_count) in chapter_by_id.items()
        if volume_id in selected_volumes or chapter_id in included_chapters
    }
    selected_ids.difference_update(excluded_chapters)
    if not selected_ids:
        raise ChapterExportSelectionError("请至少选择一个章节")

    chapters_by_volume: dict[str, list[tuple[str, str, int]]] = {
        volume.id: [] for volume in volumes
    }
    for chapter_id, (volume_id, title, word_count) in chapter_by_id.items():
        chapters_by_volume.setdefault(volume_id, []).append((chapter_id, title, word_count))

    selected_chapters = [
        (chapter_id, volume_id, title, word_count)
        for chapter_id, (volume_id, title, word_count) in chapter_by_id.items()
        if chapter_id in selected_ids
    ]
    complete_volumes = [
        volume
        for volume in volumes
        if chapters_by_volume[volume.id]
        and all(chapter_id in selected_ids for chapter_id, _title, _word_count in chapters_by_volume[volume.id])
    ]
    # 任何显式章节补集或排除集都代表零碎章节选择。即使结果恰好覆盖某卷，
    # 仍必须按章节格式导出，不能将用户的章节选择隐式提升为整卷。
    has_fragments = bool(included_chapters or excluded_chapters)
    mode = "chapters" if has_fragments else "volumes"
    nonempty_volumes = [volume for volume in volumes if chapters_by_volume[volume.id]]
    is_full_project = mode == "volumes" and len(complete_volumes) == len(nonempty_volumes)

    project_title = sanitize_filename_segment(project.title, "未命名项目")
    if is_full_project:
        filename_label = "全本"
    elif mode == "volumes" and len(complete_volumes) == 1:
        filename_label = sanitize_filename_segment(complete_volumes[0].title, "未命名卷")
    elif mode == "volumes":
        filename_label = f"{len(complete_volumes)}个卷"
    else:
        filename_label = f"{len(selected_chapters)}个章节"

    return ChapterExportPlan(
        project_id=project_id,
        filename=(
            f"{project_title}-{filename_label}-{local_date}{export_suffix(normalized_format)}"
        ),
        mode=mode,
        format=normalized_format,
        book_title=project.title or "未命名项目",
        author=settings.app_name,
        chapters=[
            ExportChapter(
                id=chapter_id,
                volume_id=volume_id,
                title=title or "未命名章节",
                word_count=word_count,
            )
            for chapter_id, volume_id, title, word_count in selected_chapters
        ],
        volumes=[
            ExportVolume(
                id=volume.id,
                title=volume.title or "未命名卷",
                order=volume.order,
                chapter_ids=[chapter_id for chapter_id, _title, _word_count in chapters_by_volume[volume.id]],
            )
            for volume in complete_volumes
        ]
        if mode == "volumes"
        else [],
    )


def get_export_summary(job: BackgroundJob) -> dict[str, object]:
    """从后台任务记录抽取前端状态所需的导出摘要。"""
    payload = background_service.parse_json_object(job.payload_json)
    progress = background_service.parse_json_object(job.progress_json)
    result = background_service.parse_json_object(job.result_json)
    error = background_service.parse_json_object(job.error_json)
    expires_at = _parse_datetime(result.get("expires_at"))
    chapter_ids = [
        chapter["id"]
        for chapter in payload.get("chapters", [])
        if isinstance(chapter, dict) and isinstance(chapter.get("id"), str)
    ]
    return {
        "id": job.id,
        "status": job.status,
        "filename": payload.get("filename", "导出章节.txt"),
        "mode": payload.get("mode", "chapters"),
        "format": payload.get("format", DEFAULT_EXPORT_FORMAT),
        "volume_count": int(payload.get("volume_count", 0)),
        "chapter_count": int(payload.get("chapter_count", len(chapter_ids))),
        "word_count": int(payload.get("word_count", 0)),
        "chapter_ids": chapter_ids,
        "current": int(progress.get("current", 0)),
        "total": int(progress.get("total", len(chapter_ids))),
        "stage": progress.get("stage") if isinstance(progress.get("stage"), str) else None,
        "chapter_title": progress.get("chapter_title")
        if isinstance(progress.get("chapter_title"), str)
        else None,
        "expires_at": expires_at,
        "error_message": error.get("message") if isinstance(error.get("message"), str) else None,
    }


class _TxtPartWriter:
    """TXT 成品的分批流式写入器（utf-8-sig，统一 \n 换行）。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file: Any = None

    async def __aenter__(self) -> "_TxtPartWriter":
        self._file = await aiofiles.open(self._path, "w", encoding="utf-8-sig", newline="\n")
        return self

    async def __aexit__(self, *_exc_info) -> None:
        await self._file.close()

    async def write_volume_heading(self, heading: str, separator: bool) -> None:
        if separator:
            await self._file.write("\n\n")
        await self._file.write(f"{heading}\n")

    async def write_chapter(self, title: str, content: str, separator: bool) -> None:
        if separator:
            await self._file.write("\n\n")
        await self._file.write(f"{title}\n{content}")


class _DocumentCollector:
    """EPUB/DOCX 的结构化收集器：按批累积卷章，收尾后一次性交给 writer。"""

    def __init__(self) -> None:
        self.volumes: list[ExportDocumentVolume] = []
        self.chapters: list[ExportDocumentChapter] = []

    async def __aenter__(self) -> "_DocumentCollector":
        return self

    async def __aexit__(self, *_exc_info) -> None:
        return None

    async def write_volume_heading(self, heading: str, separator: bool) -> None:
        self.volumes.append(ExportDocumentVolume(title=heading, order=0, chapters=[]))

    async def write_chapter(self, title: str, content: str, separator: bool) -> None:
        if self.volumes:
            self.volumes[-1].chapters.append(ExportDocumentChapter(title=title, content=content))
        else:
            self.chapters.append(ExportDocumentChapter(title=title, content=content))


async def write_chapter_export(context) -> dict[str, object]:
    """分批读取章节正文并写入任务专属导出文件（TXT/EPUB/DOCX）。"""
    payload = background_service.parse_json_object(context.job.payload_json)
    chapters = [item for item in payload.get("chapters", []) if isinstance(item, dict)]
    volumes = [item for item in payload.get("volumes", []) if isinstance(item, dict)]
    if not chapters:
        raise ChapterExportSelectionError("导出任务没有可处理的章节")

    try:
        export_format = normalize_export_format(payload.get("format"))
    except ValueError as exc:
        raise RuntimeError("导出任务格式无效") from exc
    part_path, output_path = export_file_paths(context.job_id, export_format)
    groups = {
        chapter_id: volume
        for volume in volumes
        for chapter_id in volume.get("chapter_ids", [])
        if isinstance(chapter_id, str)
    }
    mode = payload.get("mode")
    written_count = 0
    last_group_id: str | None = None
    sink = _TxtPartWriter(part_path) if export_format == "txt" else _DocumentCollector()

    try:
        async with sink:
            for offset in range(0, len(chapters), EXPORT_BATCH_SIZE):
                await context.check_cancelled()
                batch = chapters[offset : offset + EXPORT_BATCH_SIZE]
                ids = [item.get("id") for item in batch if isinstance(item.get("id"), str)]
                loaded = await chapter_repo.get_by_ids(context.session, ids)
                loaded_by_id = {chapter.id: chapter for chapter in loaded}
                if len(loaded_by_id) != len(ids):
                    raise RuntimeError("导出章节已被删除，请重新发起导出")

                for item in batch:
                    chapter_id = item.get("id")
                    if not isinstance(chapter_id, str):
                        raise RuntimeError("导出任务章节数据无效")
                    chapter = loaded_by_id[chapter_id]
                    title = item.get("title") if isinstance(item.get("title"), str) else chapter.title
                    if mode == "volumes":
                        group = groups.get(chapter_id)
                        if not isinstance(group, dict):
                            raise RuntimeError("导出任务卷数据无效")
                        group_id = group.get("id")
                        if not isinstance(group_id, str):
                            raise RuntimeError("导出任务卷数据无效")
                        if group_id != last_group_id:
                            order = group.get("order")
                            volume_title = group.get("title")
                            if not isinstance(order, int) or not isinstance(volume_title, str):
                                raise RuntimeError("导出任务卷数据无效")
                            await sink.write_volume_heading(
                                f"第{chinese_number(order)}卷 {volume_title}",
                                separator=written_count > 0,
                            )
                            last_group_id = group_id
                    content = chapter.content.replace("\r\n", "\n").replace("\r", "\n")
                    await sink.write_chapter(title, content, separator=written_count > 0)
                    written_count += 1

                last_title = batch[-1].get("title")
                context.job = await background_service.update_progress(
                    context.session,
                    context.publisher,
                    context.job,
                    current=written_count,
                    total=len(chapters),
                    message="writing",
                    extra_payload={
                        "stage": "writing",
                        "chapter_title": last_title if isinstance(last_title, str) else None,
                    },
                )
                await context.commit()

        if isinstance(sink, _DocumentCollector):
            spec_volumes = (
                sink.volumes
                if sink.volumes
                else [ExportDocumentVolume(title=None, order=1, chapters=sink.chapters)]
            )
            spec = ExportDocumentSpec(
                book_title=str(payload.get("book_title") or "导出作品"),
                author=str(payload.get("author") or "OpenFic"),
                language="zh",
                volumes=spec_volumes,
            )
            writer = write_epub if export_format == "epub" else write_docx
            await asyncio.to_thread(writer, part_path, spec)

        await context.check_cancelled()
        await asyncio.to_thread(os.replace, part_path, output_path)
        expires_at = datetime.now(UTC) + EXPORT_FILE_TTL
        return {
            "filename": payload.get("filename", "导出章节.txt"),
            "volume_count": payload.get("volume_count", 0),
            "chapter_count": len(chapters),
            "word_count": payload.get("word_count", 0),
            "expires_at": expires_at.isoformat(),
        }
    except BaseException:
        await _delete_export_files(context.job_id)
        raise


async def cleanup_chapter_export_files(session: AsyncSession) -> int:
    """清除过期或已不可达的章节导出文件（覆盖全部支持格式的成品与 .part）。"""
    directory = ensure_chapter_exports_dir()
    removed = 0
    now = datetime.now(UTC)
    paths = await asyncio.to_thread(lambda: list(directory.iterdir()))
    for path in paths:
        job_id = _job_id_from_export_path(path)
        if job_id is None:
            continue
        job = await background_service.get_job(session, job_id)
        should_keep = False
        if job is not None and job.type == EXPORT_JOB_TYPE:
            output_suffix = _output_suffix_for_job(job)
            if job.status in {
                JOB_STATUS_PENDING,
                JOB_STATUS_RUNNING,
                JOB_STATUS_CANCEL_REQUESTED,
            }:
                # 进行中的任务：.part 草稿与成品（上一轮遗留）都保留
                should_keep = path.suffix == PART_SUFFIX or path.suffix == output_suffix
            elif path.suffix == output_suffix and job.status == JOB_STATUS_SUCCEEDED:
                expires_at = _parse_datetime(
                    background_service.parse_json_object(job.result_json).get("expires_at")
                )
                should_keep = expires_at is not None and expires_at > now
        if should_keep:
            continue
        await asyncio.to_thread(path.unlink, missing_ok=True)
        removed += 1
    return removed


def is_export_download_available(job: BackgroundJob) -> bool:
    """检查任务成品是否在下载有效期内。"""
    if job.type != EXPORT_JOB_TYPE or job.status != JOB_STATUS_SUCCEEDED:
        return False
    expires_at = _parse_datetime(background_service.parse_json_object(job.result_json).get("expires_at"))
    if expires_at is None or expires_at <= datetime.now(UTC):
        return False
    _part_path, output_path = export_file_paths(job.id, _output_format_for_job(job))
    return output_path.is_file()


async def _delete_export_files(job_id: str) -> None:
    """删除任务的 .part 草稿与全部格式成品（取消/失败/超时清理）。"""
    part_path, _ = export_file_paths(job_id)
    await asyncio.to_thread(part_path.unlink, missing_ok=True)
    for suffix in EXPORT_FILE_SUFFIXES:
        await asyncio.to_thread(part_path.with_suffix(suffix).unlink, missing_ok=True)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _output_format_for_job(job: BackgroundJob) -> str:
    """按任务 payload 的 format 返回归一化格式（payload 损坏时按 TXT 兜底）。"""
    try:
        return normalize_export_format(
            background_service.parse_json_object(job.payload_json).get("format")
        )
    except ValueError:
        return DEFAULT_EXPORT_FORMAT


def _output_suffix_for_job(job: BackgroundJob) -> str:
    """按任务 payload 的 format 返回成品后缀（payload 损坏时按 TXT 兜底）。"""
    return export_suffix(_output_format_for_job(job))


def _job_id_from_export_path(path: Path) -> str | None:
    if path.suffix not in EXPORT_FILE_SUFFIXES | {PART_SUFFIX}:
        return None
    if not path.name.startswith(EXPORT_FILE_PREFIX):
        return None
    job_id = path.name[len(EXPORT_FILE_PREFIX) : -len(path.suffix)]
    return job_id or None

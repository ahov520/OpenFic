"""创作凭证报告导出任务的聚合、文件写入和清理逻辑。"""

from __future__ import annotations

import asyncio
import html
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

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
from app.core.creation_evidence import (
    CreationEvidenceNotFoundError,
    collect_creation_evidence,
)
from app.settings import settings
from app.storage.repos import chapter_repo, project_repo

EVIDENCE_JOB_TYPE = "creation_evidence_report"
EVIDENCE_FILE_PREFIX = "creation-evidence-"
EVIDENCE_FILE_TTL = timedelta(hours=24)
# HTML 明细行数上限；完整明细始终保留在 JSON 文件中。
EVIDENCE_HTML_DETAIL_LIMIT = 2000

REVISION_TYPE_LABELS = {
    "agent": "AI 生成",
    "manual": "人工",
    "rollback": "回滚",
}
REVISION_STATUS_LABELS = {
    "active": "进行中",
    "interrupted": "已中断",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
    "rollback": "回滚",
}


class CreationEvidenceReportError(RuntimeError):
    """创作凭证报告生成失败。"""


def _mapping(value: object) -> dict[str, object]:
    """把任意聚合值安全收窄为 dict。"""
    if isinstance(value, dict):
        return cast("dict[str, object]", value)
    return {}


def _seq(value: object) -> list[object]:
    """把任意聚合值安全收窄为 list。"""
    if isinstance(value, list):
        return cast("list[object]", value)
    return []


def _as_int(value: object) -> int:
    """把任意聚合值安全收窄为 int（非整数值一律视为 0）。"""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def ensure_creation_evidence_dir() -> Path:
    """确保创作凭证报告成品目录存在。"""
    settings.creation_evidence_dir.mkdir(parents=True, exist_ok=True)
    return settings.creation_evidence_dir


def evidence_file_paths(job_id: str) -> tuple[Path, Path, Path]:
    """返回任务的临时文件与 JSON/HTML 成品文件路径。"""
    directory = ensure_creation_evidence_dir()
    basename = f"{EVIDENCE_FILE_PREFIX}{job_id}"
    return (
        directory / f"{basename}.part",
        directory / f"{basename}.json",
        directory / f"{basename}.html",
    )


async def create_evidence_plan(
    session: AsyncSession,
    *,
    project_id: str,
    chapter_id: str | None,
    local_date: str,
) -> dict[str, object]:
    """校验范围并固化任务输入（含成品文件名）。"""
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise LookupError(f"项目不存在: {project_id}")

    chapter_title: str | None = None
    if chapter_id is not None:
        chapter = await chapter_repo.get_by_id(session, chapter_id)
        if chapter is None or chapter.project_id != project_id:
            raise CreationEvidenceNotFoundError(
                f"章节不存在或不属于该项目: {chapter_id}"
            )
        chapter_title = chapter.title

    filename = build_evidence_filename(
        project.title,
        chapter_title,
        local_date,
    )
    return {
        "project_id": project_id,
        "chapter_id": chapter_id,
        "filename": filename,
    }


def build_evidence_filename(
    project_title: str,
    chapter_title: str | None,
    local_date: str,
) -> str:
    """按范围生成成品文件名（不含扩展名）。"""
    from app.chapter_export.service import sanitize_filename_segment

    safe_project = sanitize_filename_segment(project_title or "未命名项目", "未命名项目")
    scope_label = (
        sanitize_filename_segment(chapter_title, "未命名章节")
        if chapter_title
        else "全本"
    )
    return f"{safe_project}-创作凭证-{scope_label}-{local_date}"


def get_evidence_summary(job: BackgroundJob) -> dict[str, object]:
    """从后台任务记录抽取前端状态所需的摘要。"""
    payload = background_service.parse_json_object(job.payload_json)
    progress = background_service.parse_json_object(job.progress_json)
    result = background_service.parse_json_object(job.result_json)
    error = background_service.parse_json_object(job.error_json)
    expires_at = _parse_datetime(result.get("expires_at"))
    return {
        "id": job.id,
        "status": job.status,
        "filename": payload.get("filename", "创作凭证报告"),
        "chapter_id": payload.get("chapter_id"),
        "current": int(progress.get("current", 0)),
        "total": int(progress.get("total", 1)),
        "stage": progress.get("stage") if isinstance(progress.get("stage"), str) else None,
        "expires_at": expires_at,
        "error_message": error.get("message") if isinstance(error.get("message"), str) else None,
    }


async def write_creation_evidence_report(context) -> dict[str, object]:
    """聚合三路数据并写入 JSON 与 HTML 成品文件。"""
    payload = background_service.parse_json_object(context.job.payload_json)
    project_id = payload.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise CreationEvidenceReportError("创作凭证任务缺少 project_id")
    chapter_id = payload.get("chapter_id")
    if chapter_id is not None and not isinstance(chapter_id, str):
        raise CreationEvidenceReportError("创作凭证任务 chapter_id 无效")
    filename = payload.get("filename")
    if not isinstance(filename, str) or not filename:
        raise CreationEvidenceReportError("创作凭证任务缺少 filename")

    part_path, json_path, html_path = evidence_file_paths(context.job_id)
    try:
        report = await collect_creation_evidence(
            context.session,
            project_id=project_id,
            chapter_id=chapter_id,
        )
        context.job = await background_service.update_progress(
            context.session,
            context.publisher,
            context.job,
            current=1,
            total=3,
            message="collecting",
            extra_payload={"stage": "collecting"},
        )
        await context.commit()

        json_bytes = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        html_bytes = render_evidence_html(report).encode("utf-8")
        context.job = await background_service.update_progress(
            context.session,
            context.publisher,
            context.job,
            current=2,
            total=3,
            message="writing",
            extra_payload={"stage": "writing"},
        )
        await context.commit()

        async with aiofiles.open(part_path, "wb") as output:
            await output.write(json_bytes)
        await asyncio.to_thread(os.replace, part_path, json_path)
        async with aiofiles.open(part_path, "wb") as output:
            await output.write(html_bytes)
        await asyncio.to_thread(os.replace, part_path, html_path)

        await context.check_cancelled()
        revision_stats = _mapping(report.get("revision_stats"))
        ai_summary = _mapping(_mapping(report.get("ai_calls")).get("summary"))
        expires_at = datetime.now(UTC) + EVIDENCE_FILE_TTL
        return {
            "filename": filename,
            "json_filename": f"{filename}.json",
            "html_filename": f"{filename}.html",
            "chapter_id": chapter_id,
            "revision_total": _as_int(revision_stats.get("total")),
            "ai_call_total": _as_int(ai_summary.get("total")),
            "expires_at": expires_at.isoformat(),
        }
    except BaseException:
        await _delete_evidence_files(context.job_id)
        raise


def is_evidence_download_available(job: BackgroundJob) -> bool:
    """检查任务成品是否在下载有效期内。"""
    if job.type != EVIDENCE_JOB_TYPE or job.status != JOB_STATUS_SUCCEEDED:
        return False
    expires_at = _parse_datetime(
        background_service.parse_json_object(job.result_json).get("expires_at")
    )
    if expires_at is None or expires_at <= datetime.now(UTC):
        return False
    _part_path, json_path, html_path = evidence_file_paths(job.id)
    return json_path.is_file() and html_path.is_file()


async def cleanup_evidence_files(session: AsyncSession) -> int:
    """清除过期或已不可达的创作凭证报告文件。"""
    directory = ensure_creation_evidence_dir()
    removed = 0
    now = datetime.now(UTC)
    paths = await asyncio.to_thread(lambda: list(directory.iterdir()))
    for path in paths:
        job_id = _job_id_from_evidence_path(path)
        if job_id is None:
            continue
        job = await background_service.get_job(session, job_id)
        should_keep = False
        if job is not None and job.type == EVIDENCE_JOB_TYPE:
            if path.suffix in {".part", ".json", ".html"}:
                if job.status in {
                    JOB_STATUS_PENDING,
                    JOB_STATUS_RUNNING,
                    JOB_STATUS_CANCEL_REQUESTED,
                }:
                    should_keep = True
                elif job.status == JOB_STATUS_SUCCEEDED:
                    expires_at = _parse_datetime(
                        background_service.parse_json_object(job.result_json).get("expires_at")
                    )
                    should_keep = expires_at is not None and expires_at > now
        if should_keep:
            continue
        await asyncio.to_thread(path.unlink, missing_ok=True)
        removed += 1
    return removed


async def _delete_evidence_files(job_id: str) -> None:
    part_path, json_path, html_path = evidence_file_paths(job_id)
    await asyncio.to_thread(part_path.unlink, missing_ok=True)
    await asyncio.to_thread(json_path.unlink, missing_ok=True)
    await asyncio.to_thread(html_path.unlink, missing_ok=True)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _job_id_from_evidence_path(path: Path) -> str | None:
    if path.suffix not in {".part", ".json", ".html"} or not path.name.startswith(
        EVIDENCE_FILE_PREFIX
    ):
        return None
    job_id = path.name[len(EVIDENCE_FILE_PREFIX) : -len(path.suffix)]
    return job_id or None


# ---------------------------------------------------------------------------
# HTML 渲染
# ---------------------------------------------------------------------------


def render_evidence_html(report: dict[str, object]) -> str:
    """把聚合 dict 渲染为自带样式的独立 HTML 报告。"""
    scope = _mapping(report.get("scope"))
    revision_stats = _mapping(report.get("revision_stats"))
    ai_calls = _mapping(report.get("ai_calls"))
    ai_summary = _mapping(ai_calls.get("summary"))
    word_activity = _mapping(report.get("word_activity"))
    revisions = _seq(report.get("revisions"))
    ai_call_items = _seq(ai_calls.get("calls"))
    by_model = _seq(ai_summary.get("by_model"))

    esc = html.escape
    scope_label = "全本（整个项目）" if not scope.get("chapter_id") else str(scope.get("chapter_title") or "")

    human_ratio = word_activity.get("human_edit_ratio")
    if isinstance(human_ratio, (int, float)):
        ratio_percent = f"{float(human_ratio) * 100:.1f}%"
        ratio_width = min(max(float(human_ratio) * 100, 0), 100)
    else:
        ratio_percent = "—"
        ratio_width = 0

    by_source = _mapping(word_activity.get("by_source"))
    source_rows = "".join(
        f"<tr><td>{esc(_source_label(source))}</td><td class='num'>{_as_int(delta):+d}</td></tr>"
        for source, delta in sorted(by_source.items())
    ) or "<tr><td colspan='2' class='empty'>暂无字数活动</td></tr>"

    by_type = _mapping(revision_stats.get("by_type"))
    type_rows = "".join(
        f"<tr><td>{esc(REVISION_TYPE_LABELS.get(str(t), str(t)))}</td><td class='num'>{count}</td></tr>"
        for t, count in by_type.items()
    ) or "<tr><td colspan='2' class='empty'>暂无版本记录</td></tr>"

    model_rows = "".join(
        "<tr>"
        f"<td>{esc(str(entry.get('model_id') or ''))}</td>"
        f"<td>{esc(str(entry.get('model_name') or ''))}</td>"
        f"<td>{esc(str(entry.get('model_provider') or ''))}</td>"
        f"<td class='num'>{entry.get('calls', 0)}</td>"
        f"<td class='num'>{entry.get('tokens_total', 0)}</td>"
        "</tr>"
        for entry in by_model
        if isinstance(entry, dict)
    ) or "<tr><td colspan='5' class='empty'>暂无 AI 调用</td></tr>"

    ai_call_rows = "".join(
        "<tr>"
        f"<td>{esc(str(call.get('created_at') or '').replace('T', ' ')[:19])}</td>"
        f"<td>{esc(str(call.get('model_id') or ''))}</td>"
        f"<td>{esc(str(call.get('operation') or ''))}</td>"
        f"<td>{esc(str(call.get('status') or ''))}</td>"
        f"<td class='num'>{call.get('tokens_input', 0)}</td>"
        f"<td class='num'>{call.get('tokens_output', 0)}</td>"
        "</tr>"
        for call in ai_call_items[:EVIDENCE_HTML_DETAIL_LIMIT]
        if isinstance(call, dict)
    ) or "<tr><td colspan='6' class='empty'>暂无 AI 调用明细</td></tr>"
    ai_truncated = ""
    if len(ai_call_items) > EVIDENCE_HTML_DETAIL_LIMIT:
        ai_truncated = (
            f"<p class='note'>明细超过 {EVIDENCE_HTML_DETAIL_LIMIT} 行，仅展示前 "
            f"{EVIDENCE_HTML_DETAIL_LIMIT} 行；完整明细见同目录 JSON 文件。</p>"
        )

    revision_rows = "".join(
        "<tr>"
        f"<td>{esc(str(revision.get('created_at') or '').replace('T', ' ')[:19])}</td>"
        f"<td>{esc(REVISION_TYPE_LABELS.get(str(revision.get('revision_type')), str(revision.get('revision_type') or '')))}</td>"
        f"<td>{esc(REVISION_STATUS_LABELS.get(str(revision.get('status')), str(revision.get('status') or '')))}</td>"
        f"<td>{esc(str(revision.get('message') or ''))}</td>"
        "<td class='num'>"
        + (
            str(revision.get("commit_count"))
            if isinstance(revision.get("commit_count"), int)
            else "—"
        )
        + "</td>"
        "</tr>"
        for revision in revisions[:EVIDENCE_HTML_DETAIL_LIMIT]
        if isinstance(revision, dict)
    ) or "<tr><td colspan='5' class='empty'>暂无修改时间线</td></tr>"
    revision_truncated = ""
    if len(revisions) > EVIDENCE_HTML_DETAIL_LIMIT:
        revision_truncated = (
            f"<p class='note'>版本记录超过 {EVIDENCE_HTML_DETAIL_LIMIT} 条，仅展示前 "
            f"{EVIDENCE_HTML_DETAIL_LIMIT} 条；完整数据见同目录 JSON 文件。</p>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(str(scope.get('project_title') or '创作凭证报告'))} · 创作凭证报告</title>
<style>
body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; margin: 0; background: #f6f7f9; color: #1f2328; }}
main {{ max-width: 1080px; margin: 0 auto; padding: 32px 24px 64px; }}
h1 {{ font-size: 26px; margin: 0 0 4px; }}
h2 {{ font-size: 18px; margin: 36px 0 12px; padding-bottom: 8px; border-bottom: 1px solid #d8dee4; }}
.meta {{ color: #57606a; font-size: 13px; margin-bottom: 8px; }}
.cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0; }}
.card {{ background: #fff; border: 1px solid #d8dee4; border-radius: 8px; padding: 14px 18px; min-width: 150px; }}
.card .value {{ font-size: 24px; font-weight: 600; }}
.card .label {{ font-size: 12px; color: #57606a; margin-top: 2px; }}
.ratio-bar {{ height: 10px; background: #eaeef2; border-radius: 5px; overflow: hidden; margin-top: 8px; }}
.ratio-bar > div {{ height: 100%; background: #0969da; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d8dee4; border-radius: 8px; overflow: hidden; font-size: 13px; }}
th, td {{ padding: 7px 10px; text-align: left; border-bottom: 1px solid #eaeef2; vertical-align: top; }}
th {{ background: #f6f8fa; font-weight: 600; white-space: nowrap; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
td.empty {{ color: #57606a; text-align: center; padding: 18px 0; }}
.note {{ color: #57606a; font-size: 12px; margin: 8px 0; }}
footer {{ color: #57606a; font-size: 12px; margin-top: 40px; border-top: 1px solid #d8dee4; padding-top: 12px; }}
</style>
</head>
<body>
<main>
<h1>创作凭证报告</h1>
<p class="meta">项目：{esc(str(scope.get('project_title') or ''))}　·　范围：{esc(scope_label)}　·　生成时间：{esc(str(report.get('generated_at') or '').replace('T', ' ')[:19])} UTC</p>
<p class="meta">报告用于披露 AI 参与情况与人工修改痕迹：修改时间线、AI 调用披露、字数活动占比均来自本地数据库的既有记录。</p>

<h2>人工修改占比</h2>
<div class="cards">
  <div class="card"><div class="value">{ratio_percent}</div><div class="label">人工修改占比（user_delta / (user + agent)）</div></div>
  <div class="card"><div class="value">{_as_int(word_activity.get('user_delta')):+d}</div><div class="label">人工增改字数（user）</div></div>
  <div class="card"><div class="value">{_as_int(word_activity.get('agent_delta')):+d}</div><div class="label">AI 增改字数（agent）</div></div>
  <div class="card"><div class="value">{_as_int(word_activity.get('events_total'))}</div><div class="label">字数活动事件数</div></div>
</div>
<div class="ratio-bar"><div style="width: {ratio_width:.1f}%"></div></div>
<p class="note">占比未包含 import 等其它来源的字数变动；分母为零时无占比。</p>
<table><thead><tr><th>来源</th><th style="text-align:right">字数变动</th></tr></thead><tbody>{source_rows}</tbody></table>

<h2>AI 调用披露</h2>
<div class="cards">
  <div class="card"><div class="value">{_as_int(ai_summary.get('total'))}</div><div class="label">调用总数</div></div>
  <div class="card"><div class="value">{_as_int(ai_summary.get('succeeded'))}</div><div class="label">成功</div></div>
  <div class="card"><div class="value">{_as_int(ai_summary.get('failed'))}</div><div class="label">失败</div></div>
  <div class="card"><div class="value">{_as_int(ai_summary.get('tokens_total'))}</div><div class="label">Tokens 总量</div></div>
</div>
<table><thead><tr><th>模型 ID</th><th>模型名称</th><th>提供商</th><th style="text-align:right">调用次数</th><th style="text-align:right">Tokens</th></tr></thead><tbody>{model_rows}</tbody></table>
<h3 style="font-size:14px; margin:20px 0 8px;">调用明细（时间 / 模型 / Tokens）</h3>
{ai_truncated}
<table><thead><tr><th>时间（UTC）</th><th>模型</th><th>操作</th><th>状态</th><th style="text-align:right">输入</th><th style="text-align:right">输出</th></tr></thead><tbody>{ai_call_rows}</tbody></table>

<h2>修改时间线</h2>
<p class="meta">版本共 {_as_int(revision_stats.get('total'))} 个：{esc('　'.join(f"{REVISION_TYPE_LABELS.get(str(t), str(t))} × {count}" for t, count in by_type.items()))}</p>
<table><thead><tr><th>类型</th><th style="text-align:right">数量</th></tr></thead><tbody>{type_rows}</tbody></table>
<h3 style="font-size:14px; margin:20px 0 8px;">版本序列</h3>
{revision_truncated}
<table><thead><tr><th>时间（UTC）</th><th>类型</th><th>状态</th><th>说明</th><th style="text-align:right">本章变更数</th></tr></thead><tbody>{revision_rows}</tbody></table>

<footer>本报告由 OpenFic 依据本地数据库生成，可用于平台创作申报存档。</footer>
</main>
</body>
</html>
"""


def _source_label(source: str) -> str:
    labels = {"user": "人工（user）", "agent": "AI（agent）", "import": "导入（import）"}
    return labels.get(source, source)

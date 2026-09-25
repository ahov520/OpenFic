# -*- coding: utf-8 -*-
"""
创作凭证聚合层 - 汇总修改时间线、AI 调用披露与字数活动。

纯只读聚合：不建新表、不做迁移，只按 project_id / chapter_id 读取
Revision/Commit、LLMAuditLog、WritingActivityEvent 三路既有数据，
产出 JSON 友好的 dict，供创作凭证报告导出与前端展示共用。
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.storage.models.chapter import Chapter
from app.storage.models.commit import Commit
from app.storage.models.llm_audit_log import LLMAuditLog
from app.storage.models.project import Project
from app.storage.models.revision import Revision
from app.storage.models.writing_activity_event import WritingActivityEvent

SCHEMA_VERSION = 1

# 参与人工修改占比计算的写作来源；import 等其它来源单列不参与。
HUMAN_RATIO_SOURCES = ("user", "agent")


@dataclass
class _ModelCallStats:
    """单模型的调用次数与 tokens 聚合。"""

    model_id: str
    model_provider: str | None
    model_name: str | None
    calls: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "calls": self.calls,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "tokens_total": self.tokens_total,
        }


class CreationEvidenceNotFoundError(LookupError):
    """项目或章节不存在。"""


def _iso(value: datetime | None) -> str | None:
    """把数据库时间统一序列化为 UTC ISO 字符串。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


async def _load_scope(
    session: AsyncSession,
    *,
    project_id: str,
    chapter_id: str | None,
) -> tuple[Project, Chapter | None]:
    project = await session.get(Project, project_id)
    if project is None:
        raise CreationEvidenceNotFoundError(f"项目不存在: {project_id}")
    chapter: Chapter | None = None
    if chapter_id is not None:
        chapter = await session.get(Chapter, chapter_id)
        if chapter is None or chapter.project_id != project_id:
            raise CreationEvidenceNotFoundError(
                f"章节不存在或不属于该项目: {chapter_id}"
            )
    return project, chapter


async def _collect_revisions(
    session: AsyncSession,
    *,
    project_id: str,
    chapter_id: str | None,
) -> list[dict[str, object]]:
    """按范围收集 revision 快照序列；单章范围附带该章 commit 计数。"""
    if chapter_id is None:
        rows = (
            await session.execute(
                select(Revision)
                .where(col(Revision.project_id) == project_id)
                .order_by(col(Revision.created_at), col(Revision.id))
            )
        ).scalars()
        commit_counts: dict[str, int] = {}
    else:
        commit_rows = (
            await session.execute(
                select(col(Commit.revision_id), func.count(col(Commit.id)))
                .where(col(Commit.chapter_id) == chapter_id)
                .group_by(col(Commit.revision_id))
            )
        ).all()
        commit_counts = {revision_id: count for revision_id, count in commit_rows}
        revision_ids = list(commit_counts)
        rows = []
        for offset in range(0, len(revision_ids), 500):
            batch_ids = revision_ids[offset : offset + 500]
            rows.extend(
                (
                    await session.execute(
                        select(Revision)
                        .where(col(Revision.id).in_(batch_ids))
                        .order_by(col(Revision.created_at), col(Revision.id))
                    )
                ).scalars()
            )

    revisions = [
        {
            "id": revision.id,
            "revision_type": revision.revision_type,
            "status": revision.status,
            "message": revision.message,
            "is_checkpoint": revision.is_checkpoint,
            "started_at": _iso(revision.started_at),
            "finished_at": _iso(revision.finished_at),
            "created_at": _iso(revision.created_at),
            "commit_count": commit_counts.get(revision.id, 0) if chapter_id else None,
        }
        for revision in rows
    ]
    return revisions


def _summarize_revisions(revisions: list[dict[str, object]]) -> dict[str, object]:
    by_type: dict[str, int] = {}
    for revision in revisions:
        revision_type = str(revision["revision_type"])
        by_type[revision_type] = by_type.get(revision_type, 0) + 1
    return {
        "total": len(revisions),
        "by_type": dict(sorted(by_type.items())),
    }


async def _collect_ai_calls(
    session: AsyncSession,
    *,
    project_id: str,
    chapter_id: str | None,
) -> dict[str, object]:
    """收集 AI 调用披露：明细 + 汇总（时间/模型/tokens/状态）。"""
    query = select(LLMAuditLog).where(col(LLMAuditLog.project_id) == project_id)
    if chapter_id is not None:
        query = query.where(col(LLMAuditLog.chapter_id) == chapter_id)
    query = query.order_by(col(LLMAuditLog.created_at), col(LLMAuditLog.id))
    logs = (await session.execute(query)).scalars()

    calls: list[dict[str, object]] = []
    succeeded = 0
    failed = 0
    tokens_input_total = 0
    tokens_output_total = 0
    tokens_total_sum = 0
    by_model: dict[str, _ModelCallStats] = {}
    for log in logs:
        calls.append(
            {
                "created_at": _iso(log.created_at),
                "model_id": log.model_id,
                "model_provider": log.model_provider,
                "model_name": log.model_name,
                "category": log.category,
                "operation": log.operation,
                "status": log.status,
                "tokens_input": log.tokens_input,
                "tokens_output": log.tokens_output,
                "tokens_total": log.tokens_total,
                "latency_ms": log.latency_ms,
                "chapter_id": log.chapter_id,
                "revision_id": log.revision_id,
            }
        )
        if log.status == "success":
            succeeded += 1
        elif log.status == "error":
            failed += 1
        tokens_input_total += log.tokens_input
        tokens_output_total += log.tokens_output
        tokens_total_sum += log.tokens_total
        stats = by_model.get(log.model_id)
        if stats is None:
            stats = _ModelCallStats(
                model_id=log.model_id,
                model_provider=log.model_provider,
                model_name=log.model_name,
            )
            by_model[log.model_id] = stats
        stats.calls += 1
        stats.tokens_input += log.tokens_input
        stats.tokens_output += log.tokens_output
        stats.tokens_total += log.tokens_total

    return {
        "summary": {
            "total": len(calls),
            "succeeded": succeeded,
            "failed": failed,
            "tokens_input": tokens_input_total,
            "tokens_output": tokens_output_total,
            "tokens_total": tokens_total_sum,
            "by_model": [
                stats.to_dict()
                for stats in sorted(by_model.values(), key=lambda s: (-s.calls, s.model_id))
            ],
        },
        "calls": calls,
    }


async def _collect_word_activity(
    session: AsyncSession,
    *,
    project_id: str,
    chapter_id: str | None,
) -> dict[str, object]:
    """按 source 汇总字数活动并计算人工修改占比。"""
    query = select(
        col(WritingActivityEvent.source),
        func.count(col(WritingActivityEvent.id)),
        func.sum(col(WritingActivityEvent.word_delta)),
    ).where(col(WritingActivityEvent.project_id) == project_id)
    if chapter_id is not None:
        query = query.where(col(WritingActivityEvent.chapter_id) == chapter_id)
    query = query.group_by(col(WritingActivityEvent.source))
    rows = (await session.execute(query)).all()

    by_source: dict[str, int] = {}
    events_total = 0
    for source, count, word_delta in rows:
        delta = int(word_delta or 0)
        by_source[str(source)] = by_source.get(str(source), 0) + delta
        events_total += int(count or 0)

    user_delta = by_source.get("user", 0)
    agent_delta = by_source.get("agent", 0)
    ratio_denominator = user_delta + agent_delta
    human_edit_ratio = (
        round(user_delta / ratio_denominator, 4) if ratio_denominator else None
    )

    return {
        "events_total": events_total,
        "by_source": dict(sorted(by_source.items())),
        "user_delta": user_delta,
        "agent_delta": agent_delta,
        "human_edit_ratio": human_edit_ratio,
        "human_edit_ratio_definition": "user_delta / (user_delta + agent_delta)",
    }


async def collect_creation_evidence(
    session: AsyncSession,
    *,
    project_id: str,
    chapter_id: str | None = None,
) -> dict[str, object]:
    """按项目或单章聚合创作凭证三路数据，返回 JSON 友好 dict。"""
    project, chapter = await _load_scope(
        session,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    revisions = await _collect_revisions(
        session,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    ai_calls = await _collect_ai_calls(
        session,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    word_activity = await _collect_word_activity(
        session,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _iso(datetime.now(UTC)),
        "scope": {
            "project_id": project.id,
            "project_title": project.title,
            "chapter_id": chapter.id if chapter is not None else None,
            "chapter_title": chapter.title if chapter is not None else None,
        },
        "revision_stats": _summarize_revisions(revisions),
        "revisions": revisions,
        "ai_calls": ai_calls,
        "word_activity": word_activity,
    }

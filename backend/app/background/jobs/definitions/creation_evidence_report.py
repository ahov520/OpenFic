"""创作凭证报告后台任务定义。"""

from typing import Any

from loguru import logger
from pydantic import BaseModel

from app.background.jobs.base import JobDefinition
from app.background.jobs.constants import (
    JOB_QUEUE_DEFAULT,
    JOB_TYPE_CREATION_EVIDENCE_REPORT,
)
from app.background.runtime.context import JobContext
from app.creation_evidence import service as creation_evidence_service


class CreationEvidenceReportInput(BaseModel):
    project_id: str
    chapter_id: str | None = None
    local_date: str


class CreationEvidenceReportResult(BaseModel):
    filename: str
    json_filename: str
    html_filename: str
    chapter_id: str | None = None
    revision_total: int
    ai_call_total: int
    expires_at: str


async def handle_creation_evidence_report(context: JobContext) -> dict[str, Any]:
    """聚合创作凭证并写入 JSON 与 HTML 报告。"""
    CreationEvidenceReportInput.model_validate(context.input)
    try:
        return await creation_evidence_service.write_creation_evidence_report(context)
    except (
        creation_evidence_service.CreationEvidenceReportError,
        creation_evidence_service.CreationEvidenceNotFoundError,
        RuntimeError,
    ):
        raise
    except Exception as exc:
        logger.bind(job_id=context.job_id).opt(exception=True).error(
            f"creation evidence report failed: {exc}"
        )
        raise RuntimeError("创作凭证报告生成失败，请重试") from exc


async def cleanup_creation_evidence_report(_context: JobContext, _reason: str) -> None:
    """取消、失败或超时时删除任务文件。"""
    await creation_evidence_service._delete_evidence_files(_context.job_id)


CREATION_EVIDENCE_REPORT_JOB = JobDefinition(
    type=JOB_TYPE_CREATION_EVIDENCE_REPORT,
    name="Creation evidence report",
    description="Aggregate AI disclosure, revision timeline and word activity into a JSON+HTML evidence report.",
    input_model=CreationEvidenceReportInput,
    result_model=CreationEvidenceReportResult,
    handler=handle_creation_evidence_report,
    on_failed=cleanup_creation_evidence_report,
    on_timeout=cleanup_creation_evidence_report,
    on_cancelled=cleanup_creation_evidence_report,
    default_queue=JOB_QUEUE_DEFAULT,
    default_timeout_seconds=600,
    default_max_attempts=1,
    supports_cancel=True,
)

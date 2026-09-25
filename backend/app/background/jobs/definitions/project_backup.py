"""整项目备份后台任务定义。"""

from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from app.background.jobs.base import JobDefinition
from app.background.jobs.constants import JOB_QUEUE_DEFAULT, JOB_TYPE_PROJECT_BACKUP
from app.background.runtime.context import JobContext
from app.project_backup import service as project_backup_service


class ProjectBackupInput(BaseModel):
    project_id: str
    filename: str


class ProjectBackupResult(BaseModel):
    filename: str
    expires_at: str
    counts: dict[str, int] = Field(default_factory=dict)


async def handle_project_backup(context: JobContext) -> dict[str, Any]:
    """打包项目全部实体为可还原的 zip。"""
    ProjectBackupInput.model_validate(context.input)
    try:
        return await project_backup_service.write_project_backup(context)
    except (project_backup_service.ProjectBackupError, LookupError, RuntimeError):
        raise
    except Exception as exc:
        logger.bind(job_id=context.job_id).opt(exception=True).error(
            f"project backup failed: {exc}"
        )
        raise RuntimeError("备份文件生成失败，请重试") from exc


async def cleanup_project_backup(_context: JobContext, _reason: str) -> None:
    """取消、失败或超时时删除任务文件。"""
    await project_backup_service._delete_backup_files(_context.job_id)


PROJECT_BACKUP_JOB = JobDefinition(
    type=JOB_TYPE_PROJECT_BACKUP,
    name="Project backup",
    description="Export an entire project as a restoreable zip archive.",
    input_model=ProjectBackupInput,
    result_model=ProjectBackupResult,
    handler=handle_project_backup,
    on_failed=cleanup_project_backup,
    on_timeout=cleanup_project_backup,
    on_cancelled=cleanup_project_backup,
    default_queue=JOB_QUEUE_DEFAULT,
    default_timeout_seconds=3600,
    default_max_attempts=1,
    supports_cancel=True,
)

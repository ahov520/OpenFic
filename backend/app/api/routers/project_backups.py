"""整项目备份 API：导出后台任务 + zip 预览 + 还原为全新项目。"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.project_backup import (
    ProjectBackupCreate,
    ProjectBackupPreviewResponse,
    ProjectBackupResponse,
    ProjectBackupRestoreResponse,
)
from app.background.jobs import service as background_service
from app.background.runtime.supervisor import get_background_supervisor
from app.project_backup import service as project_backup_service
from app.project_backup.service import ProjectBackupError
from app.storage.database import get_session


router = APIRouter(tags=["project-backups"])


@router.post(
    "/projects/{project_id}/backups",
    response_model=ProjectBackupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建整项目备份任务",
)
async def create_project_backup(
    project_id: str,
    data: ProjectBackupCreate | None = None,
    session: AsyncSession = Depends(get_session),
) -> ProjectBackupResponse:
    local_date = (
        data.local_date.isoformat()
        if data is not None and data.local_date is not None
        else date.today().isoformat()
    )
    try:
        payload = await project_backup_service.create_backup_plan(
            session, project_id=project_id, local_date=local_date
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    job = await background_service.submit_job(
        session,
        job_type=project_backup_service.BACKUP_JOB_TYPE,
        payload=payload,
        context={"project_id": project_id},
        subject_type="project",
        subject_id=project_id,
    )
    await background_service.commit_and_notify(session)
    return _to_response(job)


@router.get(
    "/projects/{project_id}/backups/{job_id}",
    response_model=ProjectBackupResponse,
    summary="获取整项目备份状态",
)
async def get_project_backup(
    project_id: str,
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectBackupResponse:
    job = await _get_backup_job(session, project_id, job_id)
    return _to_response(job)


@router.post(
    "/projects/{project_id}/backups/{job_id}/cancel",
    response_model=ProjectBackupResponse,
    summary="取消整项目备份",
)
async def cancel_project_backup(
    project_id: str,
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectBackupResponse:
    job = await _get_backup_job(session, project_id, job_id)
    job = await background_service.cancel_job(
        session,
        get_background_supervisor().create_event_publisher(),
        job,
        reason="用户取消备份",
    )
    await background_service.commit_and_notify(session)
    get_background_supervisor().cancel_running_project_backup(job.id)
    return _to_response(job)


@router.get(
    "/projects/{project_id}/backups/{job_id}/download",
    summary="下载整项目备份 zip",
)
async def download_project_backup(
    project_id: str,
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FileResponse:
    job = await _get_backup_job(session, project_id, job_id)
    if not project_backup_service.is_backup_download_available(job):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="备份文件不可用或已过期")
    _part_path, output_path = project_backup_service.backup_file_paths(job.id)
    return FileResponse(
        output_path,
        media_type="application/zip",
        filename=str(project_backup_service.get_backup_summary(job)["filename"]),
    )


@router.post(
    "/project-backups/preview",
    response_model=ProjectBackupPreviewResponse,
    summary="预览备份包内容",
)
async def preview_project_backup(
    archive: Annotated[UploadFile, File()],
) -> ProjectBackupPreviewResponse:
    data = await _read_upload(archive)
    try:
        parsed = project_backup_service.parse_backup_archive(data)
    except ProjectBackupError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProjectBackupPreviewResponse(
        kind=str(parsed.meta.get("kind")),
        schema_version=int(parsed.meta.get("schema_version", 0)),
        exported_at=parsed.meta.get("exported_at")
        if isinstance(parsed.meta.get("exported_at"), str)
        else None,
        project_title=parsed.project_title,
        counts=parsed.counts,
        total_entities=parsed.total_entities,
    )


@router.post(
    "/project-backups/restore",
    response_model=ProjectBackupRestoreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="从备份还原为全新项目",
)
async def restore_project_backup(
    archive: Annotated[UploadFile, File()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectBackupRestoreResponse:
    data = await _read_upload(archive)
    try:
        parsed = project_backup_service.parse_backup_archive(data)
        project, counts = await project_backup_service.restore_project(session, parsed)
    except ProjectBackupError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IntegrityError as exc:
        # 恶意或损坏的备份可能违反唯一约束（如两行世界书）；有回滚、无脏数据。
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="备份数据冲突，无法还原",
        ) from exc
    return ProjectBackupRestoreResponse(
        project_id=project.id,
        title=project.title,
        counts=counts,
    )


async def _read_upload(archive: UploadFile) -> bytes:
    if archive.size is not None and archive.size > project_backup_service.BACKUP_UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="备份文件过大",
        )
    data = await archive.read()
    if len(data) > project_backup_service.BACKUP_UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="备份文件过大",
        )
    return data


async def _get_backup_job(session: AsyncSession, project_id: str, job_id: str):
    job = await background_service.get_job(session, job_id)
    if (
        job is None
        or job.type != project_backup_service.BACKUP_JOB_TYPE
        or job.subject_type != "project"
        or job.subject_id != project_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="备份任务不存在")
    return job


def _to_response(job) -> ProjectBackupResponse:
    summary = project_backup_service.get_backup_summary(job)
    if project_backup_service.is_backup_download_available(job):
        summary["download_url"] = (
            f"/api/v1/projects/{job.subject_id}/backups/{job.id}/download"
        )
    return ProjectBackupResponse.model_validate(summary)

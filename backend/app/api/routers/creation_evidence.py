"""创作凭证报告 API。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.creation_evidence import (
    CreationEvidenceReportCreate,
    CreationEvidenceReportResponse,
)
from app.background.jobs import service as background_service
from app.background.runtime.supervisor import get_background_supervisor
from app.creation_evidence import service as creation_evidence_service
from app.storage.database import get_session


router = APIRouter(tags=["creation-evidence"])


@router.post(
    "/projects/{project_id}/creation-evidence-reports",
    response_model=CreationEvidenceReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建创作凭证报告任务",
)
async def create_creation_evidence_report(
    project_id: str,
    data: CreationEvidenceReportCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CreationEvidenceReportResponse:
    try:
        plan = await creation_evidence_service.create_evidence_plan(
            session,
            project_id=project_id,
            chapter_id=data.chapter_id,
            local_date=data.local_date.isoformat(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    job = await background_service.submit_job(
        session,
        job_type=creation_evidence_service.EVIDENCE_JOB_TYPE,
        payload=plan,
        context={"project_id": project_id},
        subject_type="project",
        subject_id=project_id,
    )
    await background_service.commit_and_notify(session)
    return _to_response(job)


@router.get(
    "/projects/{project_id}/creation-evidence-reports/{job_id}",
    response_model=CreationEvidenceReportResponse,
    summary="获取创作凭证报告状态",
)
async def get_creation_evidence_report(
    project_id: str,
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CreationEvidenceReportResponse:
    job = await _get_evidence_job(session, project_id, job_id)
    return _to_response(job)


@router.post(
    "/projects/{project_id}/creation-evidence-reports/{job_id}/cancel",
    response_model=CreationEvidenceReportResponse,
    summary="取消创作凭证报告",
)
async def cancel_creation_evidence_report(
    project_id: str,
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CreationEvidenceReportResponse:
    job = await _get_evidence_job(session, project_id, job_id)
    job = await background_service.cancel_job(
        session,
        get_background_supervisor().create_event_publisher(),
        job,
        reason="用户取消创作凭证报告",
    )
    await background_service.commit_and_notify(session)
    return _to_response(job)


@router.get(
    "/projects/{project_id}/creation-evidence-reports/{job_id}/download",
    summary="下载创作凭证报告文件",
)
async def download_creation_evidence_report(
    project_id: str,
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    file_format: Literal["json", "html"] = Query(
        default="html", alias="format", description="下载格式"
    ),
) -> FileResponse:
    job = await _get_evidence_job(session, project_id, job_id)
    if not creation_evidence_service.is_evidence_download_available(job):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="报告文件不可用或已过期")
    _part_path, json_path, html_path = creation_evidence_service.evidence_file_paths(job.id)
    result = background_service.parse_json_object(job.result_json)
    filename_key = "json_filename" if file_format == "json" else "html_filename"
    if file_format == "json":
        return FileResponse(
            json_path,
            media_type="application/json; charset=utf-8",
            filename=str(result.get(filename_key, "creation-evidence.json")),
        )
    return FileResponse(
        html_path,
        media_type="text/html; charset=utf-8",
        filename=str(result.get(filename_key, "creation-evidence.html")),
    )


async def _get_evidence_job(session: AsyncSession, project_id: str, job_id: str):
    job = await background_service.get_job(session, job_id)
    if (
        job is None
        or job.type != creation_evidence_service.EVIDENCE_JOB_TYPE
        or job.subject_type != "project"
        or job.subject_id != project_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="创作凭证报告任务不存在"
        )
    return job


def _to_response(job) -> CreationEvidenceReportResponse:
    summary = creation_evidence_service.get_evidence_summary(job)
    if creation_evidence_service.is_evidence_download_available(job):
        summary["json_download_url"] = (
            f"/api/v1/projects/{job.subject_id}/creation-evidence-reports/{job.id}/download"
            "?format=json"
        )
        summary["html_download_url"] = (
            f"/api/v1/projects/{job.subject_id}/creation-evidence-reports/{job.id}/download"
            "?format=html"
        )
    return CreationEvidenceReportResponse.model_validate(summary)

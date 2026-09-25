"""创作凭证报告 API 数据模型。"""

from datetime import date, datetime

from pydantic import BaseModel


class CreationEvidenceReportCreate(BaseModel):
    """创建创作凭证报告任务。"""

    chapter_id: str | None = None
    local_date: date


class CreationEvidenceReportResponse(BaseModel):
    """创作凭证报告任务状态。"""

    id: str
    status: str
    filename: str
    chapter_id: str | None = None
    current: int = 0
    total: int = 0
    stage: str | None = None
    expires_at: datetime | None = None
    json_download_url: str | None = None
    html_download_url: str | None = None
    error_message: str | None = None

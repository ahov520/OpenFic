"""整项目备份 API 数据模型。"""

from datetime import date, datetime

from pydantic import BaseModel, Field


class ProjectBackupCreate(BaseModel):
    """创建整项目备份任务。"""

    local_date: date | None = None


class ProjectBackupResponse(BaseModel):
    """整项目备份任务状态。"""

    id: str
    status: str
    filename: str
    counts: dict[str, int] = Field(default_factory=dict)
    current: int = 0
    total: int = 0
    stage: str | None = None
    expires_at: datetime | None = None
    download_url: str | None = None
    error_message: str | None = None


class ProjectBackupPreviewResponse(BaseModel):
    """备份包内容预览：还原前先看清单和计数。"""

    kind: str
    schema_version: int
    exported_at: str | None = None
    project_title: str
    counts: dict[str, int]
    total_entities: int


class ProjectBackupRestoreResponse(BaseModel):
    """还原结果：一个全新项目。"""

    project_id: str
    title: str
    counts: dict[str, int]

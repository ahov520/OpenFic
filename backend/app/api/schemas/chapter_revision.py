# -*- coding: utf-8 -*-
"""章节历史版本（revisions/commits 时间线）API schemas。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.api.schemas.chapter import ChapterResponse


class ChapterRevisionItem(BaseModel):
    """时间线条目：一次章节变更（Commit）及其所属 Revision 的类型与说明。

    每条目代表该次变更发生前保留的版本（snapshot_*），
    恢复即把该版本写回章节；operation="create" 的首条没有历史快照。
    """

    commit_id: str = Field(description="变更 ID（恢复的定位键）")
    revision_id: str = Field(description="所属版本 ID")
    revision_type: str = Field(description="版本类型：agent/manual/rollback")
    message: str = Field(description="版本描述")
    operation: str = Field(description="操作类型：create/update/delete")
    created_at: datetime = Field(description="变更时间")
    title: str | None = Field(description="该版本记录的章节标题")
    word_count: int | None = Field(description="该版本记录的章节字数")
    has_snapshot: bool = Field(description="是否携带可恢复的历史快照")


class ChapterRevisionListResponse(BaseModel):
    """章节历史版本时间线（按变更时间倒序）。"""

    items: list[ChapterRevisionItem] = Field(description="时间线条目")


class ChapterRevisionDetailResponse(ChapterRevisionItem):
    """单个版本全文预览。"""

    content: str = Field(description="该版本保留的章节全文")


class ChapterRevisionRestoreResponse(BaseModel):
    """恢复结果：写回后的章节 + 本次恢复生成的版本 ID。"""

    revision_id: str = Field(description="本次恢复创建的 manual 版本 ID")
    chapter: ChapterResponse = Field(description="恢复后的章节")

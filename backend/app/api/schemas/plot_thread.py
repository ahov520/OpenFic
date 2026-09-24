# -*- coding: utf-8 -*-
"""情节线 API 模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.storage.plot_threads import INTENT_MAX_LENGTH, NAME_MAX_LENGTH, NOTE_MAX_LENGTH

ThreadStatus = Literal["active", "resolved", "abandoned"]
BeatKind = Literal["plant", "advance", "payoff"]
PlotIssue = Literal[
    "open",
    "payoff_without_plant",
    "payoff_before_plant",
    "advance_without_plant",
    "resolved_without_payoff",
    "payoff_still_active",
]


class PlotThreadCreate(BaseModel):
    """创建情节线。"""

    name: str = Field(
        min_length=1, max_length=NAME_MAX_LENGTH, description="情节线名称"
    )
    intent: str = Field(
        default="",
        max_length=INTENT_MAX_LENGTH,
        description="一句话意图，不要写后文剧情",
    )
    status: ThreadStatus = Field(default="active", description="进行中 / 已回收 / 放弃")


class PlotThreadUpdate(BaseModel):
    """更新情节线。"""

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    intent: str | None = Field(default=None, max_length=INTENT_MAX_LENGTH)
    status: ThreadStatus | None = None


class PlotBeatCreate(BaseModel):
    """把情节线挂到某一章。"""

    chapter_id: str
    kind: BeatKind
    note: str = Field(default="", max_length=NOTE_MAX_LENGTH)


class PlotBeatUpdate(BaseModel):
    """修改某一章上的节拍。"""

    chapter_id: str | None = None
    kind: BeatKind | None = None
    note: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH)


class PlotChapterOption(BaseModel):
    """挂节拍时可选的章节。"""

    id: str
    title: str
    global_order: int
    volume_title: str


class PlotBeatResponse(BaseModel):
    """章节上的一个节拍。"""

    id: str
    thread_id: str
    chapter_id: str
    chapter_title: str
    volume_title: str
    global_order: int
    kind: BeatKind
    note: str
    created_at: datetime
    updated_at: datetime


class PlotThreadResponse(BaseModel):
    """一条情节线，以及它在哪些章出现、有什么问题。"""

    id: str
    project_id: str
    name: str
    intent: str
    status: ThreadStatus
    sort_order: int
    issues: list[PlotIssue]
    has_plant: bool
    has_payoff: bool
    last_chapter_id: str | None
    last_chapter_title: str | None
    last_global_order: int | None
    last_kind: BeatKind | None
    beats: list[PlotBeatResponse]
    created_at: datetime
    updated_at: datetime


class PlotBoardResponse(BaseModel):
    """情节线总览。"""

    threads: list[PlotThreadResponse]
    chapters: list[PlotChapterOption]

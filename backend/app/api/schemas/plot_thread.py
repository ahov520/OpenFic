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


class PlotGapChapter(BaseModel):
    """最后一次节拍和全书最后一章之间、完全没有这条线的一章。"""

    id: str
    label: str = Field(description="与总览章节称呼一致：全局阅读序. 标题")


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
    chapters_since_last: int | None = Field(
        default=None,
        description=(
            "进行中且尚未回收时，最后一次节拍到全书最后一章中间空了多少章。"
            "0 表示上一章刚出现过。已回收、已放弃，或最后一章仍在这条线上，则为空。"
            "这是相对全书末章，不是相对作者正在看的章。"
        ),
    )
    gap_chapters: list[PlotGapChapter] = Field(
        default_factory=list,
        description=(
            "进行中且没有回收节拍时，最后一次节拍所在章到全书最后一章之间、"
            "完全没有这条线节拍的章节。按卷序和卷内章节序排列，不含这两端。"
            "条数与 chapters_since_last 一致；空 0、已回收、已放弃时为空列表。"
            "前端按这个顺序展示，不要自己重排。"
        ),
    )
    gap_range: str | None = Field(
        default=None,
        description=(
            "空章超过 4 章时，卡片默认展示的首尾范围，例如「2. 对上 → 6. 结局」。"
            "不超过 4 章时为空，界面按 gap_chapters 逐章列出。展开后仍用 gap_chapters 的顺序。"
        ),
    )
    beats: list[PlotBeatResponse]
    created_at: datetime
    updated_at: datetime


class PlotBoardResponse(BaseModel):
    """情节线总览。"""

    threads: list[PlotThreadResponse]
    chapters: list[PlotChapterOption]

# -*- coding: utf-8 -*-
"""对照计划检查的响应。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PlanOrigin = Literal["synopsis", "beat"]
PlanBasis = Literal["literal", "model"]
PlanFreshness = Literal["unchecked", "current", "stale"]
PlanSource = Literal["model", "literal", "empty"]
PlanOutcome = Literal["unchecked", "no_plan", "gaps", "partial", "clear"]
BeatKind = Literal["plant", "advance", "payoff"]


class PlanCheckGap(BaseModel):
    """一条对得上梗概句子或本章节拍的缺口。"""

    ref: str = Field(description="计划条目编号")
    origin: PlanOrigin = Field(description="来自梗概或本章节拍")
    plan_text: str = Field(description="梗概原句，或这一条节拍的备注和意图")
    basis: PlanBasis = Field(description="模型判断或字面未出现")
    missing: list[str] = Field(description="正文里完全没有的专名或短句")
    detail: str = Field(description="模型说明；字面检查为空")
    beat_kind: BeatKind | None = Field(description="节拍类型")
    thread_name: str | None = Field(description="情节线名称")


class PlanCheckLine(BaseModel):
    """字面检查无法判断的一条计划。"""

    ref: str
    origin: PlanOrigin
    plan_text: str
    beat_kind: BeatKind | None = None
    thread_name: str | None = None


class PlanCheckResponse(BaseModel):
    """留在这一章上的对照结果。freshness=stale 表示正文或计划已经变了。"""

    chapter_id: str
    has_plan: bool = Field(description="当前章有梗概或本章节拍")
    freshness: PlanFreshness
    source: PlanSource | None = None
    outcome: PlanOutcome
    gaps: list[PlanCheckGap]
    unchecked: list[PlanCheckLine]
    checked_at: datetime | None = None

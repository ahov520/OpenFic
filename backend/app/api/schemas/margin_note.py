# -*- coding: utf-8 -*-
"""章节旁注 API 模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MarginNoteCreate(BaseModel):
    anchor_text: str = Field(description="选中的原文")
    context_before: str = ""
    context_after: str = ""
    body: str = Field(description="旁注，不进入正文")


class MarginNoteUpdate(BaseModel):
    status: Literal["open", "struck"] | None = None
    body: str | None = None


class MarginNoteResponse(BaseModel):
    id: str
    chapter_id: str
    anchor_text: str
    context_before: str
    context_after: str
    body: str
    status: Literal["open", "struck"]
    alignment: Literal["aligned", "misaligned"]
    start: int | None = None
    end: int | None = None
    created_at: datetime
    updated_at: datetime

# -*- coding: utf-8 -*-
"""贴在某一句上的旁注。不进入章节正文。"""

from datetime import UTC, datetime

from sqlalchemy import Column, String, Text, text
from sqlmodel import Field, SQLModel

from app.core.ids import generate_id
from app.storage.margin_notes import DEFAULT_STATUS


class ChapterMarginNote(SQLModel, table=True):
    """作者钉在选区原文上的一条旁注。"""

    __tablename__ = "chapter_margin_notes"

    id: str = Field(default_factory=generate_id, primary_key=True)
    project_id: str = Field(index=True, foreign_key="projects.id")
    chapter_id: str = Field(index=True, foreign_key="chapters.id")
    anchor_text: str = Field(sa_column=Column(Text, nullable=False))
    context_before: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default=text("''")),
    )
    context_after: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default=text("''")),
    )
    body: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(
        default=DEFAULT_STATUS,
        sa_column=Column(
            String(20),
            nullable=False,
            server_default=text("'open'"),
        ),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

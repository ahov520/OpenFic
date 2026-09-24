# -*- coding: utf-8 -*-
"""
Chapter 数据模型。
"""

from datetime import UTC, datetime

from sqlalchemy import Column, String, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel

from app.core.ids import generate_id
from app.storage.chapter_plan import DEFAULT_WRITING_STATUS


class Chapter(SQLModel, table=True):
    """
    小说章节模型。

    Attributes:
        id: 章节唯一标识符（nanoid）。
        project_id: 所属项目 ID。
        title: 章节标题。
        content: 章节正文内容。
        synopsis: 作者梗概，用来规划这一章要写什么。
        writing_status: 写作状态（idea/drafting/revising/done）。
        word_count: 章节字数，默认为 0。
        word_count_target: 本章目标字数。空表示不设目标。
        plan_check_*: 对照梗概和本章节拍的检查结果。正文、梗概或本章节拍一变就过期。
        order: 排序序号。
        created_at: 创建时间。
        updated_at: 上次修改时间。
    """

    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("volume_id", "order", name="uq_chapters_volume_order"),
    )

    id: str = Field(default_factory=generate_id, primary_key=True)
    project_id: str = Field(index=True, foreign_key="projects.id")
    volume_id: str = Field(index=True, foreign_key="volumes.id")
    title: str = Field(max_length=200)
    content: str = Field(default="")
    synopsis: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default=text("''")),
    )
    writing_status: str = Field(
        default=DEFAULT_WRITING_STATUS,
        sa_column=Column(
            String(20),
            nullable=False,
            server_default=text("'idea'"),
        ),
    )
    word_count: int = Field(default=0)
    word_count_target: int | None = Field(default=None)
    plan_check_fingerprint: str | None = Field(default=None, max_length=64)
    plan_check_source: str | None = Field(default=None, max_length=20)
    plan_check_payload: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    plan_check_at: datetime | None = Field(default=None)
    order: int = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

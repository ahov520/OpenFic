# -*- coding: utf-8 -*-
"""情节线与章节节拍。

一条情节线是作者的计划。节拍记下某一章对这条线做了埋下、推进或回收。
"""

from datetime import UTC, datetime

from sqlalchemy import Column, String, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel

from app.core.ids import generate_id
from app.storage.plot_threads import DEFAULT_THREAD_STATUS


class PlotThread(SQLModel, table=True):
    """贯穿多章的情节线或伏笔。"""

    __tablename__ = "plot_threads"

    id: str = Field(default_factory=generate_id, primary_key=True)
    project_id: str = Field(index=True, foreign_key="projects.id")
    name: str = Field(max_length=80)
    intent: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default=text("''")),
    )
    status: str = Field(
        default=DEFAULT_THREAD_STATUS,
        sa_column=Column(
            String(20),
            nullable=False,
            server_default=text("'active'"),
        ),
    )
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PlotBeat(SQLModel, table=True):
    """某一章对某条情节线做的一件事。同一章对同一条线只记一次。"""

    __tablename__ = "plot_beats"
    __table_args__ = (
        UniqueConstraint(
            "thread_id", "chapter_id", name="uq_plot_beats_thread_chapter"
        ),
    )

    id: str = Field(default_factory=generate_id, primary_key=True)
    project_id: str = Field(index=True, foreign_key="projects.id")
    thread_id: str = Field(index=True, foreign_key="plot_threads.id")
    chapter_id: str = Field(index=True, foreign_key="chapters.id")
    kind: str = Field(sa_column=Column(String(20), nullable=False))
    note: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default=text("''")),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

"""add plot threads and chapter beats

Revision ID: 1025
Revises: 1024
Create Date: 2026-09-24 02:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "1025"
down_revision: Union[str, Sequence[str], None] = "1024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plot_threads",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plot_threads_project_id"), "plot_threads", ["project_id"])
    op.create_table(
        "plot_beats",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("chapter_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["thread_id"], ["plot_threads.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "chapter_id", name="uq_plot_beats_thread_chapter"),
    )
    op.create_index(op.f("ix_plot_beats_project_id"), "plot_beats", ["project_id"])
    op.create_index(op.f("ix_plot_beats_thread_id"), "plot_beats", ["thread_id"])
    op.create_index(op.f("ix_plot_beats_chapter_id"), "plot_beats", ["chapter_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_plot_beats_chapter_id"), table_name="plot_beats")
    op.drop_index(op.f("ix_plot_beats_thread_id"), table_name="plot_beats")
    op.drop_index(op.f("ix_plot_beats_project_id"), table_name="plot_beats")
    op.drop_table("plot_beats")
    op.drop_index(op.f("ix_plot_threads_project_id"), table_name="plot_threads")
    op.drop_table("plot_threads")

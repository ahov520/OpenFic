"""add chapter margin notes

Revision ID: 1028
Revises: 1027
Create Date: 2026-09-24 12:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "1028"
down_revision: Union[str, Sequence[str], None] = "1027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chapter_margin_notes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("chapter_id", sa.String(), nullable=False),
        sa.Column("anchor_text", sa.Text(), nullable=False),
        sa.Column(
            "context_before",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "context_after",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chapter_margin_notes_project_id"),
        "chapter_margin_notes",
        ["project_id"],
    )
    op.create_index(
        op.f("ix_chapter_margin_notes_chapter_id"),
        "chapter_margin_notes",
        ["chapter_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_chapter_margin_notes_chapter_id"),
        table_name="chapter_margin_notes",
    )
    op.drop_index(
        op.f("ix_chapter_margin_notes_project_id"),
        table_name="chapter_margin_notes",
    )
    op.drop_table("chapter_margin_notes")

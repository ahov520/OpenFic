"""add character relationships

Revision ID: 1029
Revises: 1028
Create Date: 2026-09-26 16:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "1029"
down_revision: Union[str, Sequence[str], None] = "1028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "character_relationships",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("from_character_id", sa.String(), nullable=False),
        sa.Column("to_character_id", sa.String(), nullable=False),
        sa.Column("relation_type", sa.String(length=80), nullable=False, server_default=sa.text("''")),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["from_character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["to_character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_character_id",
            "to_character_id",
            name="uq_character_relationships_pair",
        ),
    )
    op.create_index(
        op.f("ix_character_relationships_project_id"),
        "character_relationships",
        ["project_id"],
    )
    op.create_index(
        op.f("ix_character_relationships_from_character_id"),
        "character_relationships",
        ["from_character_id"],
    )
    op.create_index(
        op.f("ix_character_relationships_to_character_id"),
        "character_relationships",
        ["to_character_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_character_relationships_to_character_id"),
        table_name="character_relationships",
    )
    op.drop_index(
        op.f("ix_character_relationships_from_character_id"),
        table_name="character_relationships",
    )
    op.drop_index(
        op.f("ix_character_relationships_project_id"),
        table_name="character_relationships",
    )
    op.drop_table("character_relationships")

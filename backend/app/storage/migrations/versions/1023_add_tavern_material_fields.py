"""add tavern material fields for lore triggers and preset packs

Revision ID: 1023
Revises: 1022
Create Date: 2026-09-23 22:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1023"
down_revision: Union[str, Sequence[str], None] = "1022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("world_info_entries") as batch_op:
        batch_op.add_column(sa.Column("keywords_json", sa.Text(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("is_constant", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("source", sa.String(length=40), nullable=False, server_default=""))
    with op.batch_alter_table("agent_rules") as batch_op:
        batch_op.add_column(sa.Column("origin_key", sa.String(length=200), nullable=False, server_default=""))
    with op.batch_alter_table("skills") as batch_op:
        batch_op.add_column(sa.Column("origin_key", sa.String(length=200), nullable=False, server_default=""))
    with op.batch_alter_table("revision_world_entry_snapshots") as batch_op:
        batch_op.add_column(sa.Column("keywords_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("is_constant", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("revision_world_entry_snapshots") as batch_op:
        batch_op.drop_column("source")
        batch_op.drop_column("is_constant")
        batch_op.drop_column("keywords_json")
    with op.batch_alter_table("skills") as batch_op:
        batch_op.drop_column("origin_key")
    with op.batch_alter_table("agent_rules") as batch_op:
        batch_op.drop_column("origin_key")
    with op.batch_alter_table("world_info_entries") as batch_op:
        batch_op.drop_column("source")
        batch_op.drop_column("is_constant")
        batch_op.drop_column("keywords_json")

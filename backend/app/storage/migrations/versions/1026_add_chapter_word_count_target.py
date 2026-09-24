"""add chapter word count target

Revision ID: 1026
Revises: 1025
Create Date: 2026-09-24 03:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "1026"
down_revision: Union[str, Sequence[str], None] = "1025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chapters") as batch_op:
        batch_op.add_column(sa.Column("word_count_target", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chapters") as batch_op:
        batch_op.drop_column("word_count_target")

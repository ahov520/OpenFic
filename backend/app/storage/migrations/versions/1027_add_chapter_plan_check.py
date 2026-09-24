"""add chapter plan check

Revision ID: 1027
Revises: 1026
Create Date: 2026-09-24 04:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "1027"
down_revision: Union[str, Sequence[str], None] = "1026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chapters") as batch_op:
        batch_op.add_column(
            sa.Column("plan_check_fingerprint", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("plan_check_source", sa.String(length=20), nullable=True)
        )
        batch_op.add_column(sa.Column("plan_check_payload", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("plan_check_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chapters") as batch_op:
        batch_op.drop_column("plan_check_at")
        batch_op.drop_column("plan_check_payload")
        batch_op.drop_column("plan_check_source")
        batch_op.drop_column("plan_check_fingerprint")

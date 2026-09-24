"""add chapter synopsis and writing status

Revision ID: 1024
Revises: 1023
Create Date: 2026-09-24 02:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1024"
down_revision: Union[str, Sequence[str], None] = "1023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chapters") as batch_op:
        batch_op.add_column(
            sa.Column("synopsis", sa.Text(), nullable=False, server_default=sa.text("''"))
        )
        batch_op.add_column(
            sa.Column(
                "writing_status",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'idea'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("chapters") as batch_op:
        batch_op.drop_column("writing_status")
        batch_op.drop_column("synopsis")

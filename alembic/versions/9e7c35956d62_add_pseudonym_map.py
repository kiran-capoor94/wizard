"""add pseudonym_map table

Revision ID: 9e7c35956d62
Revises: a1b2c3d4e5f6
Create Date: 2026-04-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "9e7c35956d62"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pseudonym_map",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("original_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("fake_value", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_pseudonym_map_original_hash", "pseudonym_map", ["original_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_pseudonym_map_original_hash", table_name="pseudonym_map")
    op.drop_table("pseudonym_map")

"""add transcript_raw to wizardsession

Revision ID: a9b8c7d6e5f4
Revises: f1a2b3c4d5e6
Create Date: 2026-04-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'wizardsession',
        sa.Column('transcript_raw', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('wizardsession', 'transcript_raw')

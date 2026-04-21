"""add rolling_summary to task_state

Revision ID: f1a2b3c4d5e6
Revises: e7f3a2c1b8d5
Create Date: 2026-04-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e7f3a2c1b8d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'task_state',
        sa.Column('rolling_summary', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('task_state', 'rolling_summary')

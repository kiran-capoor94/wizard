"""add observation_count to task_state

Revision ID: b8908e3438a3
Revises: 9e7c35956d62
Create Date: 2026-05-05 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'b8908e3438a3'
down_revision: Union[str, Sequence[str], None] = '9e7c35956d62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'task_state',
        sa.Column('observation_count', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('task_state', 'observation_count')

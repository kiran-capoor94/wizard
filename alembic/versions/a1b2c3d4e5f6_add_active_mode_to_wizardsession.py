"""add active_mode to wizardsession

Revision ID: a1b2c3d4e5f6
Revises: 95ee99a3db06
Create Date: 2026-04-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '95ee99a3db06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'wizardsession',
        sa.Column('active_mode', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('wizardsession', 'active_mode')

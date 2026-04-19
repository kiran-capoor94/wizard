"""add is_synthesised to wizardsession

Revision ID: d4e9f1a2b3c7
Revises: c821b5437485
Create Date: 2026-04-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'd4e9f1a2b3c7'
down_revision: Union[str, Sequence[str], None] = 'af6f28588a06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'wizardsession',
        sa.Column('is_synthesised', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('wizardsession', 'is_synthesised')

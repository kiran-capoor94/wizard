"""add agent_session_id and continued_from_id to wizardsession

Revision ID: e7f3a2c1b8d5
Revises: d4e9f1a2b3c7
Create Date: 2026-04-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'e7f3a2c1b8d5'
down_revision: Union[str, Sequence[str], None] = 'd4e9f1a2b3c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'wizardsession',
        sa.Column('agent_session_id', sa.String(), nullable=True),
    )
    op.create_index(
        'ix_wizardsession_agent_session_id',
        'wizardsession',
        ['agent_session_id'],
        unique=False,
    )
    # SQLite does not support adding FK constraints via ALTER TABLE.
    # The relationship is declared in the ORM model; here we add the column only.
    op.add_column(
        'wizardsession',
        sa.Column('continued_from_id', sa.Integer(), nullable=True),
    )
    op.create_index(
        'ix_wizardsession_continued_from_id',
        'wizardsession',
        ['continued_from_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_wizardsession_continued_from_id', table_name='wizardsession')
    op.drop_column('wizardsession', 'continued_from_id')
    op.drop_index('ix_wizardsession_agent_session_id', table_name='wizardsession')
    op.drop_column('wizardsession', 'agent_session_id')

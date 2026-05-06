"""fix_observation_note_type_case

Revision ID: 9cd1a0c203d0
Revises: drop_synthesis_columns
Create Date: 2026-05-06 12:44:15.011992

"""
from typing import Sequence, Union

from alembic import op


revision: str = '9cd1a0c203d0'
down_revision: Union[str, Sequence[str], None] = 'drop_synthesis_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE note SET note_type = 'OBSERVATION' WHERE note_type = 'observation'")


def downgrade() -> None:
    op.execute("UPDATE note SET note_type = 'observation' WHERE note_type = 'OBSERVATION'")

"""merge observation_count and vacuum_fts_rebuild heads

Revision ID: 5678ed5339a8
Revises: b8908e3438a3, vacuum_fts_rebuild
Create Date: 2026-05-05 16:12:20.835970

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '5678ed5339a8'
down_revision: Union[str, Sequence[str], None] = ('b8908e3438a3', 'vacuum_fts_rebuild')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

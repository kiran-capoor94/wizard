"""note_artifact_ref_check

Revision ID: 75c94727cfc5
Revises: 9e7c35956d62
Create Date: 2026-04-29 09:23:12.959305

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '75c94727cfc5'
down_revision: Union[str, Sequence[str], None] = '9e7c35956d62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('note', recreate='always') as batch_op:
        batch_op.create_check_constraint(
            'ck_note_has_artifact_ref',
            'artifact_id IS NOT NULL OR task_id IS NOT NULL OR session_id IS NOT NULL OR meeting_id IS NOT NULL'
        )


def downgrade() -> None:
    with op.batch_alter_table('note', recreate='always') as batch_op:
        batch_op.drop_constraint('ck_note_has_artifact_ref', type_='check')

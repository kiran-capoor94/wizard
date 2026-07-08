"""add_pid_to_wizardsession

Revision ID: 293db56f33cb
Revises: 1fd03acf7859
Create Date: 2026-07-06

Adds WizardSession.pid so SessionCloser can detect a still-live concurrent
session (a different, still-running OS process) before synthetically
auto-closing it — fixes a race where an actively-used session in another
terminal could get its summary overwritten by SessionCloser.
"""
import sqlalchemy as sa
from alembic import op

revision = "293db56f33cb"
down_revision = "1fd03acf7859"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("wizardsession") as batch_op:
        batch_op.add_column(sa.Column("pid", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("wizardsession") as batch_op:
        batch_op.drop_column("pid")

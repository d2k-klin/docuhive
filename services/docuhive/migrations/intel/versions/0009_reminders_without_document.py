"""Reminders that belong to a person instead of a document (plugin deadlines)."""

import sqlalchemy as sa
from alembic import op

revision = "0009_reminders_without_document"
down_revision = "0008_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("reminders", "document_id", nullable=True)
    op.add_column("reminders", sa.Column("owner_id", sa.BigInteger))
    op.add_column("reminders", sa.Column("link", sa.Text))
    op.create_check_constraint(
        "reminders_document_or_owner",
        "reminders",
        "document_id IS NOT NULL OR owner_id IS NOT NULL",
    )


def downgrade() -> None:
    op.execute("DELETE FROM reminders WHERE document_id IS NULL")
    op.drop_constraint("reminders_document_or_owner", "reminders")
    op.drop_column("reminders", "link")
    op.drop_column("reminders", "owner_id")
    op.alter_column("reminders", "document_id", nullable=False)

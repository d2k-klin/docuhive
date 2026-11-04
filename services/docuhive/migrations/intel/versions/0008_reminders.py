"""reminders: one row per (document, fact, remind_on) (CL-06 §7.3)."""

import sqlalchemy as sa
from alembic import op

revision = "0008_reminders"
down_revision = "0007_notify"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("document_id", sa.Text, nullable=False),
        sa.Column("fact", sa.Text, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("due_on", sa.Date, nullable=False),
        sa.Column("remind_on", sa.Date, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="scheduled"),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("document_id", "fact", "remind_on"),
    )
    op.create_index("reminders_due", "reminders", ["status", "remind_on"])
    op.create_foreign_key(
        "reminders_document_fk",
        "reminders",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_table("reminders")

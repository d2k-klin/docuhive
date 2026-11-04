"""notification_channels (Fernet config) + notification_log (CL-06 §7.1)."""

import sqlalchemy as sa
from alembic import op

revision = "0007_notify"
down_revision = "0006_chat"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("config_enc", sa.LargeBinary, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_table(
        "notification_log",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("user_id", sa.BigInteger),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("channel_id", sa.BigInteger),
        sa.Column("ok", sa.Boolean, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("dedupe_key", sa.Text),
    )
    op.create_index("notification_log_dedupe", "notification_log", ["dedupe_key", "at"])


def downgrade() -> None:
    op.drop_table("notification_log")
    op.drop_table("notification_channels")

"""chat_sessions, chat_messages, analyses (CL-05 §6.1)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0006_chat"
down_revision = "0005_chunks"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("filters", pg.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("local_only", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("route", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "session_id",
            sa.BigInteger,
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("citations", pg.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("tool_calls", pg.JSONB),
        sa.Column("flags", pg.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("ai_run_id", sa.BigInteger),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_table(
        "analyses",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("filters", pg.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("route", sa.Text),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_result", pg.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )


def downgrade() -> None:
    for t in ("chat_messages", "chat_sessions", "analyses"):
        op.drop_table(t)

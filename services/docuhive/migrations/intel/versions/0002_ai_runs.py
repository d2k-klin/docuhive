"""ai_runs: every model attempt (CL-01 §1.6). CHECK enforces AI-03."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0002_ai_runs"
down_revision = "0001_intel"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "ai_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("task", sa.Text, nullable=False),
        sa.Column("document_id", sa.Text),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("local", sa.Boolean, nullable=False),
        sa.Column("restricted", sa.Boolean, nullable=False),
        sa.Column("prompt_version", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("tokens_in", sa.Integer),
        sa.Column("tokens_out", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(10, 5)),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("output", pg.JSONB),
        sa.Column("error", sa.Text),
        sa.CheckConstraint("NOT restricted OR local", name="restricted_is_local"),
    )
    op.create_index("ai_runs_doc", "ai_runs", ["document_id"])
    op.create_index("ai_runs_month", "ai_runs", ["provider", "at"])
    op.create_foreign_key(
        "ai_runs_document_fk", "ai_runs", "documents", ["document_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_table("ai_runs")

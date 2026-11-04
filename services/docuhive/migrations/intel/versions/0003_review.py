"""review_items: AI suggestions waiting for a person (CL-02 §2.5)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0003_review"
down_revision = "0002_ai_runs"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "review_items",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("document_id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("field", sa.Text),
        sa.Column("suggested", pg.JSONB),
        sa.Column("current", pg.JSONB),
        sa.Column("confidence", sa.Float),
        sa.Column("reason", sa.Text),
        sa.Column("evidence", sa.Text),
        sa.Column("ai_run_id", sa.BigInteger),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", sa.BigInteger),
    )
    op.create_index(
        "review_pending",
        "review_items",
        ["status", "created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "review_one_pending",
        "review_items",
        ["document_id", "kind", "field"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_foreign_key(
        "review_document_fk",
        "review_items",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "review_ai_run_fk", "review_items", "ai_runs", ["ai_run_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_table("review_items")

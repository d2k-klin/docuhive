"""Holds: a document, or some of its fields, made unchangeable for a reason and a time."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_holds"
down_revision = "0005_plugins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_holds",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "document_id",
            sa.Text(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("fields", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("until", sa.Date()),
        sa.Column("placed_by", sa.Text(), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lifted_at", sa.DateTime(timezone=True)),
        sa.Column("lifted_by", sa.Text()),
        sa.Column("lift_reason", sa.Text()),
    )
    op.create_index("document_holds_document", "document_holds", ["document_id"])


def downgrade() -> None:
    op.drop_table("document_holds")

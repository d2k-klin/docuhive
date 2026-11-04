"""Custom fields, saved views and near-duplicate pairs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_archive_tools"
down_revision = "0002_knowledge_bases"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "custom_fields",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "document_types", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column(
            "remind_days_before",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{}",
        ),
        *timestamps(),
        sa.CheckConstraint("type IN ('money','date','string','number','iban')"),
    )
    op.create_table(
        "saved_views",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("owner_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        *timestamps(),
    )
    op.create_index("ix_saved_views_owner_id", "saved_views", ["owner_id"])
    op.create_table(
        "duplicate_pairs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("document_id", sa.Text(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("other_id", sa.Text(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reasons", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.UniqueConstraint("document_id", "other_id", name="duplicate_pairs_pair"),
        sa.CheckConstraint("document_id < other_id"),
        sa.CheckConstraint("status IN ('open','dismissed','confirmed')"),
    )
    op.create_index("ix_duplicate_pairs_document_id", "duplicate_pairs", ["document_id"])
    op.create_index("ix_duplicate_pairs_other_id", "duplicate_pairs", ["other_id"])


def downgrade() -> None:
    op.drop_table("duplicate_pairs")
    op.drop_table("saved_views")
    op.drop_table("custom_fields")

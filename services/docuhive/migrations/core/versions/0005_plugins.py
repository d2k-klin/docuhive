"""Plugins: which installed plugins are switched on, and what they were allowed to do."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_plugins"
down_revision = "0004_document_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plugins",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("version", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("enabled_at", sa.DateTime(timezone=True)),
        sa.Column("enabled_by", sa.Text()),
        sa.Column("granted", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("last_error", sa.Text()),
        sa.Column("migration", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("plugins")

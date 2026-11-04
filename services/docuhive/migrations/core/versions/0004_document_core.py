"""AI provenance per document, written to meta.json under `ai.<task>`."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_document_core"
down_revision = "0003_archive_tools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "ai_provenance",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_index("documents_status", "documents", ["status"])


def downgrade() -> None:
    op.drop_index("documents_status", table_name="documents")
    op.drop_column("documents", "ai_provenance")

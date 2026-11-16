"""Documents a plugin generated: which plugin, and the documents they were made from."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_generated_documents"
down_revision = "0006_holds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("doc_sources", sa.Column("generator", sa.Text()))
    op.add_column(
        "doc_sources",
        sa.Column(
            "derived_from",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_index(
        "doc_sources_derived_from", "doc_sources", ["derived_from"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("doc_sources_derived_from", "doc_sources")
    op.drop_column("doc_sources", "derived_from")
    op.drop_column("doc_sources", "generator")

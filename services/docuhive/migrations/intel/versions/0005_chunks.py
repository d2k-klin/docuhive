"""doc_chunks with pgvector + HNSW (CL-05 §5.2)."""

import sqlalchemy as sa
from alembic import op

revision = "0005_chunks"
down_revision = "0004_mail"
branch_labels = None
depends_on = None

NOW = sa.text("now()")

DIMS = 1024  # = tasks.embed.dims; another size needs a new migration + `docuhive index rebuild`


def upgrade() -> None:
    from pgvector.sqlalchemy import Vector

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "doc_chunks",
        sa.Column("document_id", sa.Text, primary_key=True),
        sa.Column("chunk_no", sa.Integer, primary_key=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(DIMS), nullable=False),
        sa.Column("embed_model", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_foreign_key(
        "chunks_document_fk", "doc_chunks", "documents", ["document_id"], ["id"], ondelete="CASCADE"
    )
    op.execute(
        "CREATE INDEX doc_chunks_hnsw ON doc_chunks USING hnsw "
        "(embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.drop_table("doc_chunks")

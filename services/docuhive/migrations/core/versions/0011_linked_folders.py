"""Where a document came from in more detail, and folders DocuHive reads without moving files."""

import sqlalchemy as sa
from alembic import op

revision = "0011_linked_folders"
down_revision = "0010_guest_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, kind in (
        ("uploaded_by", sa.Text()),  # the person who uploaded or captured it
        ("device", sa.Text()),  # "iPhone · Safari", from the browser that sent it
        ("folder", sa.Text()),  # scanner subfolder, or a linked folder's label
        ("path", sa.Text()),  # where in that folder
        ("file_modified_at", sa.DateTime(timezone=True)),  # the file's own date
    ):
        op.add_column("doc_sources", sa.Column(name, kind))
    op.create_table(
        "linked_folders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("path", sa.Text(), nullable=False, unique=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_scan_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
    )
    op.create_table(
        "linked_files",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "folder_id",
            sa.BigInteger(),
            sa.ForeignKey("linked_folders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("mtime_ns", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.Text(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        # linked: analysed and in the archive; duplicate: the same file was already there;
        # skipped: not a document DocuHive reads; failed: could not be read; missing: gone
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("folder_id", "path"),
        sa.CheckConstraint(
            "state IN ('linked', 'duplicate', 'skipped', 'failed', 'missing')",
            name="linked_files_state",
        ),
    )


def downgrade() -> None:
    op.drop_table("linked_files")
    op.drop_table("linked_folders")
    for name in ("file_modified_at", "path", "folder", "device", "uploaded_by"):
        op.drop_column("doc_sources", name)

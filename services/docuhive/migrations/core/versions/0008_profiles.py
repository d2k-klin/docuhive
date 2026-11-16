"""Identities ("profiles"): who the household or business is when it writes or sends something."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_profiles"
down_revision = "0007_generated_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    jsonb = postgresql.JSONB()
    op.create_table(
        "profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("shared", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("legal_form", sa.Text()),
        sa.Column("address", jsonb, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("email", sa.Text()),
        sa.Column("phone", sa.Text()),
        sa.Column("website", sa.Text()),
        sa.Column("tax_number", sa.Text()),
        sa.Column("vat_id", sa.Text()),
        sa.Column("tax_office", sa.Text()),
        sa.Column("bank", jsonb, nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "logo_document_id", sa.Text(), sa.ForeignKey("documents.id", ondelete="SET NULL")
        ),
        sa.Column("extra", jsonb, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("smtp", jsonb),  # host, port, username, from; the password sits in smtp_secret
        sa.Column("smtp_secret", sa.LargeBinary()),  # Fernet, the mail token key
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("kind IN ('person', 'business', 'household')", name="profiles_kind"),
    )


def downgrade() -> None:
    op.drop_table("profiles")

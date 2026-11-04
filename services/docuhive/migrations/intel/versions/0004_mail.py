"""Mail accounts, message ledger, attachments, backfills (CL-04 §4.2)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0004_mail"
down_revision = "0003_review"
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "mail_accounts",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("owner_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("address", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text),
        sa.Column("enc_credentials", sa.LargeBinary, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("sync_cursor", pg.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("label_on_import", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("default_shared", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("provider", "address"),
    )
    op.create_table(
        "mail_messages",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "account_id",
            sa.BigInteger,
            sa.ForeignKey("mail_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_msg_id", sa.Text, nullable=False),
        sa.Column("rfc_message_id", sa.Text),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email_from", sa.Text),
        sa.Column("subject", sa.Text),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("triage_confidence", sa.Float),
        sa.Column("ai_run_id", sa.BigInteger),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("account_id", "provider_msg_id"),
    )
    op.create_index(
        "mail_messages_status", "mail_messages", ["account_id", "status", "received_at"]
    )
    op.create_table(
        "mail_attachments",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "message_id",
            sa.BigInteger,
            sa.ForeignKey("mail_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_att_id", sa.Text),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("mime", sa.Text),
        sa.Column("size", sa.Integer),
        sa.Column("sha256", sa.Text),
        sa.Column("document_id", sa.Text),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
    )
    op.create_index("mail_attachments_sha", "mail_attachments", ["sha256"])
    op.create_index("mail_attachments_doc", "mail_attachments", ["document_id"])
    op.create_table(
        "backfills",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "account_id",
            sa.BigInteger,
            sa.ForeignKey("mail_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_from", sa.Date, nullable=False),
        sa.Column("date_to", sa.Date, nullable=False),
        sa.Column("page_token", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="running"),
        *[
            sa.Column(c, sa.Integer, nullable=False, server_default="0")
            for c in ("scanned", "candidates", "imported", "duplicates", "errors")
        ],
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
    )


def downgrade() -> None:
    for t in ("backfills", "mail_attachments", "mail_messages", "mail_accounts"):
        op.drop_table(t)

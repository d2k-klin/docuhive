"""Mail tables: accounts, the message ledger, attachments, backfills. Intel migration 0003."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from docuhive.ai.types import BigId, Json
from docuhive.db import IntelBase


class MailAccount(IntelBase):
    __tablename__ = "mail_accounts"
    __table_args__ = (UniqueConstraint("provider", "address"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigId)
    provider: Mapped[str] = mapped_column(Text)  # gmail | graph | imap
    address: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    enc_credentials: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(Text, default="active")  # active|paused|needs_reauth|error
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_cursor: Mapped[dict] = mapped_column(Json, default=dict)
    label_on_import: Mapped[bool] = mapped_column(Boolean, default=False)
    default_shared: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MailMessage(IntelBase):
    __tablename__ = "mail_messages"
    __table_args__ = (
        UniqueConstraint("account_id", "provider_msg_id"),
        Index("mail_messages_status", "account_id", "status", "received_at"),
    )
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("mail_accounts.id", ondelete="CASCADE"))
    provider_msg_id: Mapped[str] = mapped_column(Text)
    rfc_message_id: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    email_from: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    # new | prefiltered_out | triage_rejected | imported | partial | error
    status: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    triage_confidence: Mapped[float | None] = mapped_column(Float)
    ai_run_id: Mapped[int | None] = mapped_column(BigId)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MailAttachment(IntelBase):
    __tablename__ = "mail_attachments"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("mail_messages.id", ondelete="CASCADE"))
    provider_att_id: Mapped[str | None] = mapped_column(Text)  # null = body-as-document
    filename: Mapped[str] = mapped_column(Text)
    mime: Mapped[str | None] = mapped_column(Text)
    size: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[str | None] = mapped_column(Text)
    # skipped | submitted | duplicate | stored | quarantined | error
    status: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)


class Backfill(IntelBase):
    __tablename__ = "backfills"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("mail_accounts.id", ondelete="CASCADE"))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    page_token: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, default="running"
    )  # running|paused|done|cancelled|error
    scanned: Mapped[int] = mapped_column(Integer, default=0)
    candidates: Mapped[int] = mapped_column(Integer, default=0)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

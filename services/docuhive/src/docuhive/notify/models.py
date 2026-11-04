"""notification_channels + notification_log. Intel migration 0006."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, LargeBinary, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from docuhive.ai.types import BigId
from docuhive.db import IntelBase


class NotificationChannel(IntelBase):
    __tablename__ = "notification_channels"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigId)
    kind: Mapped[str] = mapped_column(Text)  # ntfy | email | <plugin kind>
    config_enc: Mapped[bytes] = mapped_column(LargeBinary)  # Fernet(JSON config)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationLog(IntelBase):
    __tablename__ = "notification_log"
    __table_args__ = (Index("notification_log_dedupe", "dedupe_key", "at"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[int | None] = mapped_column(BigId)
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    channel_id: Mapped[int | None] = mapped_column(BigId)
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(Text)

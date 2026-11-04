"""reminders: one row per (document, fact, remind_on). Intel migration 0007."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from docuhive.ai.types import BigId
from docuhive.db import IntelBase


class Reminder(IntelBase):
    __tablename__ = "reminders"
    __table_args__ = (UniqueConstraint("document_id", "fact", "remind_on"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(Text)
    fact: Mapped[str] = mapped_column(Text)  # fact name, or "notice_deadline"
    label: Mapped[str] = mapped_column(Text)
    due_on: Mapped[date] = mapped_column(Date)
    remind_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, default="scheduled")  # scheduled|sent|dismissed|done
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

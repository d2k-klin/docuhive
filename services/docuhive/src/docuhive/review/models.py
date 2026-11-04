"""review_items: AI suggestions waiting for a person. Intel migration 0002."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from docuhive.ai.types import BigId, Json
from docuhive.db import IntelBase


class ReviewItem(IntelBase):
    __tablename__ = "review_items"
    __table_args__ = (
        Index(
            "review_pending",
            "status",
            "created_at",
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        Index(
            "review_one_pending",
            "document_id",
            "kind",
            "field",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)  # field | new_term | notice
    field: Mapped[str | None] = mapped_column(Text)  # category, facts.amount_total, tag:<value>
    suggested: Mapped[Any | None] = mapped_column(Json)  # {"value": ..., "currency": ..., "type"}
    current: Mapped[Any | None] = mapped_column(Json)
    confidence: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    ai_run_id: Mapped[int | None] = mapped_column(BigId)
    status: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[int | None] = mapped_column(BigId)

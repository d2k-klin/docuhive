"""ai_runs: one row per model attempt (successful or not). Intel migration 0001."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from docuhive.ai.types import BigId, Json
from docuhive.db import IntelBase


class AIRun(IntelBase):
    __tablename__ = "ai_runs"
    __table_args__ = (
        # AI-03 at the database level: restricted input is never logged as a cloud run.
        CheckConstraint("NOT restricted OR local", name="restricted_is_local"),
        Index("ai_runs_doc", "document_id"),
        Index("ai_runs_month", "provider", "at"),
    )
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    task: Mapped[str] = mapped_column(Text)
    document_id: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    local: Mapped[bool] = mapped_column(Boolean)
    restricted: Mapped[bool] = mapped_column(Boolean)
    prompt_version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # ok | invalid | error | timeout | skipped
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 5))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    output: Mapped[Any | None] = mapped_column(Json)
    error: Mapped[str | None] = mapped_column(Text)

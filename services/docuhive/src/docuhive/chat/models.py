"""chat_sessions, chat_messages, analyses. Intel migration 0005."""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from docuhive.ai.types import BigId, Json, TextArray
from docuhive.db import IntelBase


class ChatSession(IntelBase):
    __tablename__ = "chat_sessions"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigId)
    title: Mapped[str | None] = mapped_column(Text)
    filters: Mapped[dict] = mapped_column(Json, default=dict)  # SearchFilters scope
    local_only: Mapped[bool] = mapped_column(Boolean, default=False)
    route: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(IntelBase):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(Text)  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[str]] = mapped_column(TextArray, default=list)
    tool_calls: Mapped[Any | None] = mapped_column(Json)  # [{name, args, summary, result?}]
    flags: Mapped[dict] = mapped_column(Json, default=dict)  # {uncited, truncated, limited}
    ai_run_id: Mapped[int | None] = mapped_column(BigId)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Analysis(IntelBase):
    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigId)
    name: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str] = mapped_column(Text)
    filters: Mapped[dict] = mapped_column(Json, default=dict)
    route: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_result: Mapped[Any | None] = mapped_column(
        Json
    )  # {markdown, citations, facts_rows, ai_run_id}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

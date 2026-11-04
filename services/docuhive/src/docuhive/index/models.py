"""doc_chunks: embedded chunks for semantic search. Intel migration 0004."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from docuhive.ai.types import vector
from docuhive.db import IntelBase

# ponytail: the dimension is fixed per column; another embedding size needs a migration plus
# `docuhive index rebuild`. Fine at personal scale.
DIMS = 1024


class DocChunk(IntelBase):
    __tablename__ = "doc_chunks"
    document_id: Mapped[str] = mapped_column(Text, primary_key=True)
    chunk_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(vector(DIMS))
    embed_model: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

"""Split a document into ~800-token chunks, each prefixed with a metadata header."""

import re

from docuhive.contracts import DocumentView

CHUNK_CHARS = 3200
OVERLAP_CHARS = 400


def header(view: DocumentView) -> str:
    """The vectors carry context: 'Title/Type/Category/...' before every chunk."""
    return (
        f"Title: {view.title or ''}\nType: {view.document_type or ''}\n"
        f"Category: {view.category or ''}\nCorrespondent: {view.correspondent or ''}\n"
        f"Date: {view.document_date.isoformat() if view.document_date else ''}\n---\n"
    )


def split(content: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n|\f", content) if p.strip()]
    step = size - overlap - 2  # room for the carried-over tail
    pieces: list[str] = []
    for p in paras:  # hard-split paragraphs longer than the limit
        pieces += [p[i : i + step] for i in range(0, len(p), step)] if len(p) > size else [p]
    chunks: list[str] = []
    current = ""
    for p in pieces:
        if current and len(current) + len(p) + 2 > size:
            chunks.append(current)
            tail = current[-overlap:]  # carry the tail over for continuity, if it fits
            current = f"{tail}\n\n{p}" if len(tail) + len(p) + 2 <= size else p
        else:
            current = f"{current}\n\n{p}" if current else p
    if current:
        chunks.append(current)
    return chunks


def chunk(view: DocumentView, content: str) -> list[str]:
    head = header(view)
    return [head + c for c in split(content)] or [head.rstrip("-\n")]

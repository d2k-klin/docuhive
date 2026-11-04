"""Document contract; implemented with the selected archive backend in OA-M3."""

from collections.abc import Iterator
from datetime import datetime

from docuhive.contracts import (
    ApplyResult,
    CurrentUser,
    DocStatus,
    DocumentView,
    MetadataPatch,
    Provenance,
    SearchFilters,
)


class NotFound(Exception):
    pass


def get(doc_id: str) -> DocumentView:
    raise NotImplementedError("OA-M3")


def get_for_user(doc_id: str, user: CurrentUser) -> DocumentView:
    raise NotImplementedError("OA-M4")


def get_content(doc_id: str, max_chars: int | None = None) -> str:
    raise NotImplementedError("OA-M3")


def apply_metadata(
    doc_id: str,
    patch: MetadataPatch,
    *,
    actor: str,
    provenance: Provenance | None = None,
    force: bool = False,
) -> ApplyResult:
    raise NotImplementedError("OA-M3")


def iter_ids(
    *,
    status: DocStatus = DocStatus.stored,
    added_since: datetime | None = None,
    filters: SearchFilters | None = None,
) -> Iterator[str]:
    raise NotImplementedError("OA-M3")

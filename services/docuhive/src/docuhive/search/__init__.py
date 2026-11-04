"""Search contract; semantic providers register through this module."""

from collections.abc import Callable
from typing import Literal

from docuhive.contracts import CurrentUser, SearchFilters, SearchHit, SemanticHit

SemanticFn = Callable[[CurrentUser, str, SearchFilters, int], list[SemanticHit]]
_semantic: SemanticFn | None = None


def register_semantic(fn: SemanticFn) -> None:
    global _semantic
    _semantic = fn


def hybrid(
    user: CurrentUser,
    query: str,
    filters: SearchFilters,
    limit: int = 20,
    mode: Literal["hybrid", "fts", "semantic"] = "hybrid",
) -> list[SearchHit]:
    raise NotImplementedError("OA-M4")

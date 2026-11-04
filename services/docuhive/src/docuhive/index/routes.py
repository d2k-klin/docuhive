"""GET /api/ai/similar/{id} and /api/ai/semantic-search (for testing before OA's hybrid search)."""

from fastapi import APIRouter, Query

from docuhive import documents
from docuhive.ai.http import User, fail, summary
from docuhive.contracts import SearchFilters
from docuhive.index import semantic

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/similar/{document_id}")
def similar(document_id: str, user: User, k: int = Query(default=8, ge=1, le=50)) -> dict:
    try:
        documents.get_for_user(document_id, user)
    except documents.NotFound:
        fail(404, "not_found", "Document not found")
    items = [
        summary(documents.get(h.document_id)) | {"score": round(h.score, 4)}
        for h in semantic.similar(user, document_id, k)
    ]
    return {"items": items, "semantic_available": semantic.available()}


@router.get("/semantic-search")
def semantic_search(user: User, q: str, k: int = Query(default=10, ge=1, le=50)) -> dict:
    hits = semantic.semantic_search(user, q, SearchFilters(), k)
    return {"items": [h.model_dump() for h in hits], "semantic_available": semantic.available()}

"""index.embed {document_id}: chunk, embed and replace the document's chunks atomically."""

from typing import Any

from sqlalchemy import delete, select

from docuhive import db, documents, jobs, taxonomy
from docuhive.agents.pipeline import guarded
from docuhive.ai import privacy
from docuhive.ai.embeddings import embedder
from docuhive.contracts import DocStatus
from docuhive.duplicates import queue_scan
from docuhive.index.chunking import chunk
from docuhive.index.models import DIMS, DocChunk


def embed_document(doc_id: str) -> dict:
    view = documents.get(doc_id)
    if view.status != DocStatus.stored or view.deleted_at:
        return {"skipped": "not stored"}
    emb = embedder()
    restricted = privacy.is_restricted(view, taxonomy.load())
    if emb is None or (restricted and not emb.route.local):
        # Restricted + cloud embedder: never embedded; drop chunks from before it was restricted.
        with db.session() as s:
            s.execute(delete(DocChunk).where(DocChunk.document_id == doc_id))
        return {"skipped": "no allowed embedder" if emb is None else "restricted"}
    if emb.dims != DIMS:
        raise jobs.PermanentFailure(
            f"tasks.embed.dims={emb.dims} but doc_chunks.embedding is vector({DIMS})"
        )
    texts = chunk(view, documents.get_content(doc_id))
    vectors = emb.embed(texts, document_id=doc_id, restricted=restricted)
    with db.session() as s:  # one transaction: delete old, insert new
        s.execute(delete(DocChunk).where(DocChunk.document_id == doc_id))
        s.add_all(
            DocChunk(
                document_id=doc_id, chunk_no=i, text=t, embedding=v, embed_model=str(emb.route)
            )
            for i, (t, v) in enumerate(zip(texts, vectors, strict=True))
        )
    return {"chunks": len(texts)}


@jobs.handler("index.embed", queue="ai", timeout_s=900)
def run_embed(payload: dict, ctx: Any) -> None:
    doc_id = payload["document_id"]
    guarded(doc_id, ctx, embed_document, doc_id)
    queue_scan(doc_id)  # after embedding, so content similarity is one of the signals


def rebuild(missing_only: bool = False) -> int:
    """Enqueue index.embed for every stored document (initial backfill or a model change)."""
    with db.session() as s:
        have = set(s.scalars(select(DocChunk.document_id).distinct())) if missing_only else set()
    n = 0
    for doc_id in documents.iter_ids():
        if doc_id not in have:
            jobs.enqueue(
                "index.embed", {"document_id": doc_id}, queue="ai", dedupe_key=f"embed:{doc_id}"
            )
            n += 1
    return n

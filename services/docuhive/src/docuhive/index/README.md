# `services/docuhive/src/docuhive/index`

**Overview.** Semantic search: chunking documents, embedding them, and finding similar documents.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Package marker |
| [`chunking.py`](chunking.py) | Split a document into ~800-token chunks, each prefixed with a metadata header |
| [`filters.py`](filters.py) | Re-exports the shared filter builder from `docuhive.search.filters` |
| [`jobs.py`](jobs.py) | index.embed {document_id}: chunk, embed and replace the document's chunks atomically |
| [`models.py`](models.py) | doc_chunks: embedded chunks for semantic search |
| [`routes.py`](routes.py) | GET /api/ai/similar/{id} and /api/ai/semantic-search (semantic-only, for testing) |
| [`semantic.py`](semantic.py) | Semantic search (best chunk per document), chunk-level search for knowledge bases, and similar documents over doc_chunks |

## Extending

Every query must apply the visibility rule; restricted documents are embedded only by local models.

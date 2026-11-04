# `services/docuhive/src/docuhive/search`

**Overview.** Full-text, hybrid and knowledge-base chunk search, and the registration points for semantic search. Results from both sides are fused with reciprocal rank fusion (RRF).

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | The search contract: `hybrid` (documents), `retrieve` (chunks for knowledge bases), `rrf`, and `register_semantic` / `register_chunk_semantic` |
| [`filters.py`](filters.py) | `SearchFilters` to SQL conditions; the one filter builder for full-text and semantic search |
| [`fts.py`](fts.py) | PostgreSQL full-text candidates for documents and chunks: German/English/simple configurations, trigram typo fallback, highlighted snippets |

## Extending

Apply filters and visibility in every result list.

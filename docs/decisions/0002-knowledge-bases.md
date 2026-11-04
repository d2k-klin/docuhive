# Decision: a Bedrock-style knowledge base inside DocuHive

Date: 2026-11-04 · State: proposed

## Context

We want a self-hosted knowledge base that works like Amazon Bedrock Knowledge Bases. In Bedrock that means:

- named knowledge bases fed by data sources
- ingestion jobs with a visible status
- chunking and embeddings
- metadata filters
- a `Retrieve` API (ranked chunks) and a `RetrieveAndGenerate` API (an answer with citations)

that any agent or app can call. It has to run on the always-on Mac mini (32 GB RAM) next to Ollama, with the archive on the NAS.

An external analysis proposed adding a separate KB platform next to the archive: RAGFlow, Open WebUI, Dify or AnythingLLM, or a custom LlamaIndex + Qdrant service. That analysis assumed Paperless-ngx as the archive. DocuHive replaced Paperless with its own core, and that core already contains most of a knowledge base.

| Bedrock KB capability | DocuHive today |
| --- | --- |
| Data sources and sync | Mail sync and backfill, upload, phone capture, scanner folder and API tokens, all through `ingest.submit` |
| Parsing | OCRmyPDF + Tesseract, Gotenberg for office files, safe content detection |
| Chunking | `index/chunking.py`: ~800-token chunks with overlap and a metadata header |
| Embeddings | `index.embed` job routed through the harness (`bge-m3`, 1024 dimensions, local by default) |
| Vector store | `doc_chunks` in PostgreSQL with a pgvector HNSW index |
| Metadata filters | `SearchFilters`: categories, types, correspondents, tags, dates, sources, documents |
| Permissions | every query goes through the visibility rule (`auth.visible_docs`) |
| Retrieve and generate | the Ask agent: `search_documents`, `read_document`, `query_facts`, `list_vocabulary`, with citations |
| Privacy | restricted documents only reach local models; enforced by `CHECK (NOT restricted OR local)` on `ai_runs` |

What is missing: hybrid ranking (`search.hybrid` is still a stub), **named knowledge bases**, a **retrieval API for other agents**, an **MCP server**, ingestion **status per knowledge base**, and **retrieval evals**.

## Options

| Option | For | Against |
| --- | --- | --- |
| **RAGFlow** | Closest to Bedrock's shape; strong parsing of complex PDFs and tables | Needs ≥ 16 GB RAM for its own services, Elasticsearch or Infinity, MinIO and Redis; no ARM64 images, so we would build and maintain our own; parses and stores a second copy of every document |
| **Open WebUI** | Light; Ollama-native; good chat UI | A KB *inside a chat app*, not a service; since v0.6.6 its licence forbids removing its branding; its external pgvector store is experimental |
| **Dify** | KBs plus workflows and agents | Heavy; its licence restricts multi-tenant use and removing its logo; a second platform to run |
| **AnythingLLM** | Easiest to install | Workspace-oriented; sync features in preview; again a second copy of the documents |
| **LlamaIndex + Qdrant service** | Full control of the API | Adds a vector database and a large framework to do what our chunker, pgvector and harness already do |
| **Extend DocuHive's own index (chosen)** | Reuses the pipeline, vault, permissions, privacy gate, harness and Postgres; no new services | We build the KB API and UI ourselves |

Every external platform shares the same three problems:

1. **Copies.** It would re-parse and store the archive a second time, outside the vault, which breaks "the vault is the source of truth".
2. **Permissions.** It knows nothing about our users and visibility rules, so a sync service would have to copy them and keep them current.
3. **Privacy.** It would embed and answer over health and identity documents with whatever model it is configured for, outside our privacy gate.

## Decision

Build the knowledge base **inside DocuHive**, on the existing PostgreSQL + pgvector index, and expose it with Bedrock's shape:

- **A knowledge base is a named, saved scope over the one index**: a `SearchFilters` plus a description and privacy settings, such as "Insurance", "Finance" or "Property". There are no copies and no second index, and retrieval is always `visible_docs ∩ kb.filters`.
- **Hybrid retrieval at chunk level**: full-text (unaccented German/English configurations, trigram) and vector search fused with reciprocal rank fusion, with an optional local reranker that is switched on only if evals show it helps.
- **Two APIs, as in Bedrock**: `POST /api/kb/{id}/retrieve` returns ranked chunks with document links and metadata, and `POST /api/kb/{id}/ask` returns an answer with citations through the existing Ask agent.
- **An MCP server** (`docuhive mcp`) with `kb_list`, `kb_retrieve`, `kb_ask` and `document_read`, so Claude Code, Strands agents, Open WebUI or any MCP client can use the knowledge bases.
- **Privacy across the API boundary**: DocuHive cannot see where an API caller sends the text, so restricted documents are excluded from API and MCP results unless the token is explicitly marked *local-only consumer*. This is the same masking the Ask agent already applies to cloud routes.
- **Status like Bedrock's ingestion jobs**: per knowledge base, show documents indexed, pending, failed and stale, plus the embedding model, from the existing job table.

Open WebUI stays an option **as a front end only**: it can call `kb_retrieve` over MCP, while the documents never leave DocuHive.

## Validation and consequences

- **Memory on the Mac mini.** PostgreSQL, API and worker: about 2 GB. `bge-m3` embeddings: about 1.2 GB. An optional `bge-reranker-v2-m3`: about 1.1 GB. A routine chat model in the 8B class: about 6 GB. That totals about 10 GB, leaving room for macOS and a larger model loaded on demand. RAGFlow alone would ask for 16 GB.
- **No new services.** The knowledge base adds tables, endpoints, a CLI command and a UI page, not containers.
- **Quality is measured, not assumed.** A retrieval eval (questions → expected documents, recall@5, MRR) gates changes to chunking, hybrid weights and the reranker.
- **Revisit** if the archive grows to millions of chunks, if complex tables need RAGFlow-class parsing (that would be a better parser inside `ingest`, not a second platform), or if knowledge bases must hold content that is not documents (for example crawled websites). In that last case, add a data-source type that feeds `ingest.submit`.

The implementation plan is in [shared/knowledge-bases.md](../shared/knowledge-bases.md).

# Knowledge bases: implementation plan

**Overview.** How DocuHive gets Bedrock-style knowledge bases: named scopes over the one index, hybrid chunk retrieval, `retrieve` and `ask` APIs, an MCP server for other agents, and status and evals. The reasoning and the options considered are in [decision 0002](../decisions/0002-knowledge-bases.md). The requirement IDs (KB-01…KB-08) are in [REQUIREMENTS.md §5.16](../REQUIREMENTS.md#516-knowledge-bases-kb).

## Principles

1. **One index, many knowledge bases.** A knowledge base is a saved `SearchFilters` with a name, description and privacy settings. It never copies documents or chunks.
2. **Retrieval is `visible_docs ∩ kb.filters`.** The same permission and privacy rules as search and chat. No new code path may skip them.
3. **Nothing leaves without the privacy rule.** API and MCP callers get restricted chunks only with a token marked *local-only consumer*. Otherwise those documents are excluded, the way the Ask agent masks them for cloud routes.
4. **Quality is measured.** Chunking, fusion weights and the reranker change only with a retrieval eval result.
5. **No new services.** Postgres, the worker and the API do all of it. The reranker, if enabled, runs in the worker on CPU or MPS.

## Milestones

The KB work starts after OA-M4 (hybrid search) and CL-M6 (ask). Like the rest of the plan, the milestones have no dates. Each owner moves at their own pace, and consumers build against the listed fallback.

| ID | Owner | What | Needs |
| --- | --- | --- | --- |
| **KB-M1** | OA | Chunk-level hybrid retrieval | OA-M4 |
| **KB-M2** | OA | Knowledge bases: table, CRUD API, defaults from the taxonomy | KB-M1 |
| **KB-M3** | CL | `retrieve` and `ask` APIs, token privacy | KB-M2 (fallback: filters only) |
| **KB-M4** | CL | MCP server | KB-M3 |
| **KB-M5** | CL | Retrieval evals and optional reranker | KB-M1 |
| **KB-M6** | OA (page) + CL (test panel, Ask scope) | Knowledge-bases UI | KB-M2, KB-M3 |
| **KB-M7** | QA | Contract, permission, privacy and journey tests | each milestone as it lands |

### KB-M1 Chunk-level hybrid retrieval (OA)

- `doc_chunks` is CL's table (intel migrations), so **CL** adds `doc_chunks.tsv tsvector` in an intel migration (I13). It is filled by `index.embed` with the document's language configuration (`dh_german`, `dh_english`, `dh_simple`) and has a GIN index. Until then, OA computes `to_tsvector(...)` over the chunk text at query time, which is slower but gives the same results.
- `search.retrieve(user, query, filters, k=20, mode="hybrid") -> list[ChunkHit]` in the search contract:
  - full-text candidates: `websearch_to_tsquery`, `ts_rank_cd`, with `pg_trgm` on titles and senders for typos
  - vector candidates: `register_semantic` (I8), top 50
  - fusion: reciprocal rank fusion, `score = Σ 1 / (60 + rank)`, then grouped so one document cannot fill the result
- `search.hybrid` (documents) becomes a thin wrapper that groups `retrieve` hits by document, so search and knowledge bases share one ranking.
- `ChunkHit` (new contract model): `document_id`, `chunk_no`, `text`, `score`, `title`, `document_date`, `category`, `page` (when known), `url`.
- **Done when:** unit tests cover RRF ordering and grouping; an integration test on the test stack shows a German stemmed term, a typo and a paraphrase each finding the right synthetic document.

### KB-M2 Knowledge bases (OA)

- Core table `knowledge_bases`:
  - `id`, `name`, `description`, `filters jsonb` (a `SearchFilters`), `owner_id`, `shared bool`
  - `local_only bool`: answers for this knowledge base use local models only
  - `created_at`, `updated_at`
- API: `GET/POST /api/kb`, `GET/PATCH/DELETE /api/kb/{id}`. Validation rejects unknown categories, tags and types (taxonomy, I7).
- Defaults: on first run, offer one knowledge base per top-level category that has documents ("Insurance", "Finance", "Property", …), plus "Everything". These are suggestions in the setup checklist, not created silently.
- Status (`GET /api/kb/{id}/status`), from existing tables:
  - documents in scope, and how many of them are embedded
  - pending, failed and stale (embedded with an older model than `routing.yaml` names)
  - last indexed time, embedding model
- **Done when:** CRUD with permission tests (owner, shared, other user), and status numbers match a seeded fixture.

### KB-M3 Retrieve and ask APIs (CL)

- `POST /api/kb/{id}/retrieve` with `{query, k ≤ 50, filters?}`. Filters can only narrow the knowledge base, never widen it. It returns `ChunkHit[]`, the knowledge-base name and the embedding model.
- `POST /api/kb/{id}/ask` with `{question, session_id?}`. It runs the existing Ask agent with `scope = kb.filters` (∩ request filters) and `local_only = kb.local_only or request.local_only`. It streams SSE like `/api/chat`, and its result carries `ai_run_id` for the "How was this made?" page.
- Token scopes `kb:read` (retrieve) and `kb:ask` (ask), on top of AUTH-02.
- Privacy:
  - tokens get a `local_consumer` flag, off by default, which a user can only set in the UI
  - without it, documents where `is_restricted` is true are excluded from `retrieve`, and the excluded count is reported as `excluded_restricted: n`, never the content
  - `ask` follows the harness as today, restricted documents only with local routes
- Rate limit per token. Every `retrieve` call is logged (token, knowledge base, hit count, excluded count) next to `ai_runs`, for the AI settings page.
- **Done when:** contract tests for both endpoints, and a privacy test: a restricted fixture document never appears for a normal token and does appear for a `local_consumer` token.

### KB-M4 MCP server (CL)

- `docuhive mcp` uses the official `mcp` Python SDK:
  - stdio, for Claude Code and local agents
  - streamable HTTP at `/mcp`, behind the same token auth
- Tools, thin wrappers over KB-M3:

  | Tool | What it does |
  | --- | --- |
  | `kb_list` | knowledge bases the token can see |
  | `kb_retrieve(kb, query, k)` | ranked chunks with links |
  | `kb_ask(kb, question)` | an answer with citations |
  | `document_read(document_id, max_chars)` | text of one visible document |

- The same privacy rule as KB-M3. Tool descriptions say what each returns and that results cite document URLs.
- Docs: connecting Claude Code, a Strands agent (MCP client) and Open WebUI (as a front end only).
- **Done when:** an MCP client test lists tools and calls `kb_retrieve` over stdio and HTTP; `examples/learn/` gets a runnable Strands agent using DocuHive as its knowledge base.

### KB-M5 Retrieval evals and reranker (CL)

- `evals/retrieval/`: a synthetic set of questions with expected document IDs, in German and English, including paraphrases, typos, dates and amounts. The golden set from real documents stays in the overlay.
- Metrics: recall@5, recall@20, MRR, per mode (fts, semantic, hybrid) and per knowledge base. The baseline is committed like the other evals.
- Experiments, each kept only if the eval improves:
  - chunk size (3200 vs 1600 characters)
  - with and without the metadata header
  - RRF k
  - a reranker on the top 20: `bge-reranker-v2-m3` via `sentence-transformers` in the worker, routed as a `rerank` task in `routing.yaml`, local only
- **Done when:** `make eval` reports retrieval metrics, the CI eval gate covers changes to `index/` and `search/`, and decision 0002 records the measured result.

### KB-M6 Knowledge-bases UI (OA page, CL panels)

- `/knowledge`:
  - the list of knowledge bases with status (indexed / pending / failed / stale) and the embedding model
  - create and edit from the same filter controls as search
  - the privacy setting
- **Test panel** (like Bedrock's console): a query box showing the ranked chunks with scores, the mode used and the excluded-restricted count. It shows what retrieval returns before an agent relies on it.
- Ask: a knowledge-base scope chip next to the category and model selects.
- Settings → API tokens: the `kb:read` and `kb:ask` scopes and the *local-only consumer* switch, with plain-language help.
- Follows the `docuhive-ui` and `guided-experience` skills: empty states with one next action, and controls at one height.
- **Done when:** `make qa-e2e` covers create → status → test panel → ask in scope, at all widths and in both themes.

### KB-M7 Verification (QA)

- Contract tests for `ChunkHit`, the KB API and the MCP tool schemas.
- Permission matrix: owner, shared and other user × knowledge base × token scope.
- Privacy: restricted fixtures across retrieve, ask, MCP, and normal and local-consumer tokens.
- Journey: seeded documents → a knowledge base → retrieve via the API and MCP → ask with citations.
- Resource check on the reference machine (Mac mini, 32 GB): API + worker + Postgres + embeddings + an 8B chat model under a backfill. Record peak memory in the verification report.

## Integration points

| ID | Provider → Consumer | What | Fallback until ready |
| --- | --- | --- | --- |
| **I10** | OA → CL | `search.retrieve` + `ChunkHit` | CL's semantic-only retrieval over `doc_chunks` |
| **I11** | OA → CL | `knowledge_bases` table and `kb.get(user, id)` | an in-memory knowledge base from a `SearchFilters` passed in the request |
| **I12** | CL → OA | `/api/kb/{id}/retrieve` for the test panel | the panel calls `/api/ai/semantic-search` |
| **I13** | CL → OA | `doc_chunks.tsv` + GIN index (intel migration) | `to_tsvector` computed at query time |

## Reference machine budget

| Process | Memory (approx.) |
| --- | --- |
| PostgreSQL, API, worker, web | 2 GB |
| `bge-m3` embeddings (Ollama) | 1.2 GB |
| `bge-reranker-v2-m3` (optional, worker) | 1.1 GB |
| 8B-class chat model (Ollama, quantized) | 6 GB |
| **Total** | **≈ 10 GB of 32 GB** |

A larger model for hard questions is loaded on demand. Ollama unloads idle models.

## Out of scope

- Separate KB platforms (RAGFlow, Dify, AnythingLLM) or an extra vector database: see decision 0002.
- Non-document data sources (web crawling, wikis). If needed later, they become an ingest source, so their content lands in the vault like any document.
- Multi-tenant hosting.

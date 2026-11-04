# CL-05 — Embeddings, semantic search, Ask, analyses (CL-M5, CL-M6)

## CL-M5 — Embeddings + semantic search + similar documents

**Goal:** meaning-based search (SRCH-02, SRCH-05) and the retrieval half of Ask.
**Uses:** I3 (`documents.get/get_content`, events), I5 (`visible_docs`, `register_semantic`). Until I5 is done, filter by `owner_id == user.id` and expose your own `/api/ai/semantic-search` for testing.
**Provides:** I8.

### 5.1 Embedder — `docuhive/ai/embeddings.py`
Strands has no embeddings API, so write a tiny client per provider (these are the only places with a provider-specific HTTP call):
```python
class Embedder(Protocol):
    route: Route; dims: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...   # batch, order-preserving
```
| Kind | Call |
|------|------|
| ollama | `POST {host}/api/embed {model, input: [...]}` |
| openai (and compatible) | `POST {base}/v1/embeddings {model, input}` |
| bedrock | `bedrock-runtime.invoke_model` (Titan v2 / Cohere multilingual) |

- Routing: `tasks.embed` in `routing.yaml` (`route`, `dims`, `batch` with default 32).
- Every batch call is logged to `ai_runs` (`task=embed`, tokens if reported, `output` null).
- **Privacy:** restricted documents may only be embedded with a `local: true` embedder. Otherwise they are **not embedded**: they are excluded from semantic search and still found by FTS. Query text is embedded with the same embedder. If `local_only` is on and the embedder is cloud, semantic search is disabled.

### 5.2 Table (intel migration `0004_chunks`)
```sql
CREATE TABLE doc_chunks (
  document_id  text NOT NULL,            -- FK documents(id) ON DELETE CASCADE
  chunk_no     int NOT NULL,
  text         text NOT NULL,
  embedding    vector(1024) NOT NULL,    -- = tasks.embed.dims
  embed_model  text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (document_id, chunk_no)
);
CREATE INDEX doc_chunks_hnsw ON doc_chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```
`ponytail:` the dimension is fixed per column. Changing to an embedding model with different dims means a migration plus `docuhive index rebuild` (a full re-embed). That is acceptable at personal scale.

### 5.3 Chunking + indexing — `docuhive/index/`
- `chunk(view: DocumentView, content: str) -> list[str]`:
  - Split on blank lines and page breaks (`\f`) into paragraphs. Greedily pack them into chunks of about 3200 chars (~800 tokens), with 400 chars of overlap. Hard-split any paragraph longer than the limit.
  - **Prefix every chunk** with a metadata header so the vectors carry context:
    `Title: …\nType: …\nCategory: …\nCorrespondent: …\nDate: …\n---\n`
- Job `index.embed {document_id}` (queue `ai`, dedupe `embed:<id>`):
  1. Load the view and content. Skip if the status is not `stored` or the document is trashed.
  2. Apply the privacy check.
  3. Chunk, then embed in batches.
  4. In **one transaction**, `DELETE` the old chunks and `INSERT` the new ones.
- **Triggers** (from CL-02 §2.2): after classify/extract, on `metadata_changed` (title, correspondent, category, type, date), and on `document.stored` with the rebuild hint.
- **Trash/restore:** there is no need to touch the chunks, because `visible_docs` excludes trashed documents. **Purge** deletes them (FK cascade).
- `docuhive index rebuild [--missing-only] [--model …]` enqueues `index.embed` for `documents.iter_ids()`, with a progress output. It is used for the initial backfill of existing documents.

### 5.4 Semantic search fn (I8) — `docuhive/index/semantic.py`
```python
def semantic_search(user, query, filters, k) -> list[SemanticHit]:
    qv = embedder.embed([query])[0]
    # SQL (SQLAlchemy Core):
    # SELECT c.document_id, c.chunk_no, c.text, 1 - (c.embedding <=> :qv) AS score
    # FROM doc_chunks c JOIN documents d ON d.id = c.document_id
    # WHERE <auth.visible_docs(user)> AND <filters on d.*>
    # ORDER BY c.embedding <=> :qv LIMIT :k * 4
    # -> keep best chunk per document, top k documents
```
- Set `SET LOCAL hnsw.ef_search = 100` for recall.
- Filters reuse OA's filter semantics. Import OA's `filters_sql` helper **only if** OA exposes it in contracts. Until then, re-implement the subset you need (categories, document_types, date range, tags) in `index/filters.py`, with a `ponytail:` note to switch to OA's helper.
- Register it in `docuhive.ai.startup()`: `search.register_semantic(semantic_search)`.

### 5.5 Similar documents — `GET /api/ai/similar/{document_id}?k=8`
- **Document vector:** the mean of its chunk embeddings (computed in SQL with `avg(embedding)`, which pgvector supports).
- Then nearest documents, excluding the document itself, with `visible_docs` applied. The response has `items: DocumentSummary + score`.
- `components/intel/SimilarDocuments.tsx` renders up to 8 thumbnails with titles. It shows nothing if the list is empty or semantic search is unavailable.
- `components/intel/SearchModeHint.tsx`: if `semanticAvailable` is false, show a one-line hint ("Semantic search is off — configure an embedding model in Settings → AI").

### 5.6 Tests & eval
- Chunker: overlap, header prefix, a long paragraph split, empty content.
- Index job: re-embed replaces the chunks atomically; a restricted document with a cloud embedder gets no chunks.
- Semantic search:
  - permissions (another user's private document never returned, even when it is the nearest)
  - filters
  - best-chunk-per-document
- Eval: `docuhive eval search` on the synthetic set. Targets: recall@10 for hybrid ≥ FTS-only + 10 points, and hybrid ≥ 0.85 on the synthetic set.

### Acceptance
- "the letter about my pension change" finds the right document in the top 5 (golden or manual check), where FTS alone does not.
- "Similar documents" shows the other electricity invoices for an electricity invoice.
- **I8 marked done.** OA's `/api/search` reports `semantic_available=true`.

---

## CL-M6 — Ask agent, facts tool, chat UI, analyses

**Goal:** chat with citations, and numbers computed by SQL (QA-01..04, QA-06).
**Uses:** I5 `search.hybrid` and `get_for_user` (fallback: your own semantic search + `documents.get`, with the owner check), and I6 SSE through the proxy (fallback in dev: the browser calls the Python API directly via `NEXT_PUBLIC_DEV_DIRECT_API`).

### 6.1 Tables (intel migration `0005_chat`)
```sql
CREATE TABLE chat_sessions (
  id bigserial PRIMARY KEY, user_id bigint NOT NULL, title text,
  filters jsonb NOT NULL DEFAULT '{}',          -- SearchFilters scope
  local_only boolean NOT NULL DEFAULT false,
  route text,                                    -- chosen provider/model, null = default
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE chat_messages (
  id bigserial PRIMARY KEY, session_id bigint NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role text NOT NULL,                            -- user | assistant | tool
  content text NOT NULL,
  citations text[] NOT NULL DEFAULT '{}',        -- document ids
  tool_calls jsonb,                              -- [{name, args, result_summary}]
  ai_run_id bigint, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE analyses (
  id bigserial PRIMARY KEY, user_id bigint NOT NULL, name text NOT NULL,
  prompt text NOT NULL, filters jsonb NOT NULL DEFAULT '{}', route text,
  last_run_at timestamptz, last_result jsonb,    -- {markdown, citations, facts_rows, ai_run_id}
  created_at timestamptz NOT NULL DEFAULT now());
```

### 6.2 Tools — `docuhive/agents/tools/` (Strands `@tool`; each tool receives the user + session scope through a closure, never from the model)
| Tool | Signature (model-facing) | Implementation |
|------|--------------------------|----------------|
| `search_documents` | `(query: str, category?: str, document_type?: str, date_from?: str, date_to?: str, limit: int = 10)` | `search.hybrid(user, query, session_filters ∧ args)`. Returns `[{id, title, date, type, correspondent, snippet}]` |
| `read_document` | `(document_id: str, max_chars: int = 6000)` | `documents.get_for_user`, then `get_content`. Returns metadata + facts + text |
| `query_facts` | `(field: str, agg: "sum"\|"avg"\|"min"\|"max"\|"count"\|"list", document_type?: str, category?: str, correspondent?: str, date_from?: str, date_to?: str, group_by?: "month"\|"year"\|"correspondent"\|"category")` | SQL over `doc_facts` ⨝ `documents`, with `visible_docs(user)` + the session filters. Dates apply to `document_date`. **Money aggregates are grouped by currency** (never summing across currencies). Returns `{rows: [{document_id, title, date, value, currency}] (≤ 200), aggregates: [{group, currency, value, count}]}` |
| `list_vocabulary` | `()` | taxonomy categories and types (with their fact fields), plus the top 100 correspondents |

**Privacy inside tools:** if the active route is non-local and a document is restricted, `read_document` returns `{id, title: "[restricted]", content: "Content withheld: this document is restricted to local models."}`. `search_documents` returns the id with the title masked. The agent is told this in the system prompt. With `local_only` on, the session uses only local routes, and everything is visible.

### 6.3 Ask agent — `docuhive/agents/ask.py`, prompt `prompts/ask.md`
Rules in the system prompt:
- Answer only from tool results. Cite every claim as `[doc:<id>]`.
- **Numbers and totals must come from `query_facts`.** Never add numbers yourself. Show the per-currency results and say which documents were included.
- If nothing relevant is found, say so. Don't guess. Suggest a refined search.
- Answer in the language of the question.
- Keep tool loops bounded: max 8 tool calls per turn (enforced by the harness).

How a turn runs:
- `run_agent("chat", "ask", {...}, tools, history)` streams events. History is the last 20 messages of the session; older ones are summarised once, into the session's first system message.
- **Post-processing:**
  1. Extract the `[doc:…]` ids.
  2. Drop ids that the user cannot see (defence in depth).
  3. Store them as `citations`.
  4. If the answer has factual content but no citations, set the flag `uncited: true` (QA-02).

### 6.4 Chat API — `/api/chat`
| Endpoint | Notes |
|----------|-------|
| `POST /api/chat/sessions {title?, filters?, local_only?, route?}` · `GET /api/chat/sessions` · `GET/PATCH/DELETE /api/chat/sessions/{id}` | owner only |
| `GET /api/chat/sessions/{id}/messages` | |
| `POST /api/chat/sessions/{id}/messages {content}` | returns `text/event-stream` |

SSE events (JSON `data:`):
```
event: token        data: {"text": "…"}
event: tool_call    data: {"name": "query_facts", "args": {...}}
event: tool_result  data: {"name": "query_facts", "summary": "12 rows, EUR 1012.40"}
event: citation     data: {"document_id": "01J…", "title": "…"}
event: done         data: {"message_id": 123, "ai_run_id": 456, "uncited": false, "usage": {...}}
event: error        data: {"code": "budget_exceeded" | "no_allowed_route" | "provider_error", "message": "…"}
```
- Send a heartbeat comment `: ping` every 15 s.
- If the client disconnects, the generation is cancelled, and a partial message is stored with `truncated`.
- `GET /api/chat/routes` returns the routes this user may pick for chat (from `tasks.chat` + fallbacks, with local flags), shown in the UI selector.

### 6.5 Ask UI — `app/(app)/ask/` (CL)
- **Session list** on the left (on mobile, a drawer), with a "New chat" button.
- **Scope bar:** filter chips (category, type, date range) and a "Local only" toggle (forced on with a lock icon if `privacy.local_only` is set). A model selector shows the local badge.
- **Messages:**
  - markdown rendering (`react-markdown` with `rehype-sanitize`; no raw HTML)
  - `[doc:ID]` rendered as chips with title and thumbnail on hover, linking to `/documents/ID`
  - tool activity collapsed by default ("Searched documents · Queried facts (12 rows)")
  - `query_facts` results rendered as a small table under the answer (from the `tool_result` and the stored message)
  - a warning label on `uncited` answers
- Streaming through `fetch` + `ReadableStream`. No EventSource, because a POST body is needed. Stop with an abort button.
- **Suggestions** on an empty chat: "How much did I spend on electricity in 2025?", "Which contracts can I cancel in the next 3 months?", "Show my insurance policies and their premiums".
- Nav: uncomment "Ask".

### 6.6 Saved analyses (QA-04) — `/api/analyses` + `app/(app)/analyses/`
- **CRUD** on `analyses`. `POST /api/analyses/{id}/run` runs the Ask agent non-interactively (`task=analyse`, so it can have its own route), with the stored prompt and filters, and stores `last_result`. It runs as a job; the UI polls.
- **Built-in templates** (`config/defaults/analyses.yaml`; the overlay can add more):
  - "Utilities spend by month (this year)"
  - "Contracts ending or renewable in the next 90 days"
  - "Insurance overview: policies, premiums, renewal dates"
  - "Tax-relevant documents for year X"
- The analyses page has a list with the last run time, "Run", and a result view (the same rendering as chat).

### 6.7 Chat UX (the [`document-chat` skill](../../.agents/skills/document-chat/SKILL.md) is binding)
- **Entry params:** `/ask?q=` (prefill and send), `?document_id=` (scope `document_ids`), `?filters=` (an encoded `SearchFilters`). OA's ⌘K palette, documents list and detail page link here.
- **`GET /api/chat/suggestions`:** 3–6 questions built from the user's archive (top categories × document types with facts, from templates in `config/defaults/chat-suggestions.yaml`), so a user with no utility invoices never sees an electricity question.
- **Follow-ups:** the ask prompt ends with a structured trailer (`<followups>["…","…"]</followups>`). The harness parses and validates it (max 3, max 80 chars, no ids), and strips it from the text. It is sent as an SSE event `followups`.
- **Clarifying questions:** if the agent returns a `clarify` trailer (`{"question": "…", "options": ["Car","Home","Health"]}`), the UI shows the options as chips.
- **Feedback:** add `feedback jsonb` to `chat_messages` (`{rating: up|down, reason?, at}`), with `POST /api/chat/messages/{id}/feedback`. `docuhive eval export-qa --feedback down --out overlay/evals/qa-candidates.yaml` turns 👎 answers into eval candidates.
- **"Open as list"** → `/documents?ids=<comma ids>` (OA supports `document_ids`). **"Save as analysis"** on any answer.
- **No-results and masked notices** follow the table in the skill. Restricted-masking is announced via an SSE event `notice` `{kind: "restricted_masked", count}`.

### 6.8 Tests & eval
- `query_facts`:
  - sum by currency
  - group by month and year
  - date filters
  - permissions
  - session filter intersection
  - money is never summed across currencies
- Tools: restricted masking with a cloud route, full content with a local route.
- Agent (FakeModel scripted tool calls): citations extracted, invisible ids dropped, uncited flag, max tool calls enforced.
- SSE: the event order, the heartbeat, cancellation on disconnect (httpx streaming test).
- `docuhive eval ask` on `qa.yaml` (synthetic plus golden). Targets: number correctness ≥ 95% on the facts questions, citation recall ≥ 0.8, uncited answers ≤ 5%.

### Acceptance (J4)
- "How much did I spend on electricity in 2025?" streams an answer with a per-currency total from `query_facts`, a table of the invoices included, and citations to each. The total equals the SQL check.
- A user's chat never cites another user's private document (test with two users and the same query).
- A restricted document with a cloud chat route is masked. Switching to "Local only" shows it.
- The saved analysis "Contracts ending in 90 days" runs and lists the right contracts.

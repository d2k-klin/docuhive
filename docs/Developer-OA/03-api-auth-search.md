# OA-03 — Auth, permissions, REST API, search (OA-M4)

**Goal:** a secure multi-user API over the documents, plus full-text and hybrid search. **Unblocks:** I5.

## 4.1 Auth — `docuhive/auth/`

### Users & passwords
- Passwords are hashed with argon2id (`argon2-cffi` defaults). The minimum length is 12. Hashes are rehashed on login if the parameters changed.
- `docuhive user create|passwd|disable`. **No sign-up endpoint**: an admin creates users (CLI or the settings UI).

### Sessions (browser)
- `POST /api/auth/login {username, password}` → `204` and a `Set-Cookie: dh_session=<token>`:
  - the token is 32 random bytes, base64url
  - `HttpOnly; Secure` (except `ENV=dev`)`; SameSite=Lax; Path=/; Max-Age=30d`
- The DB stores `sha256(token)` only. Sessions slide: `last_seen_at`, and `expires_at` is extended when less than 15 days remain.
- `POST /api/auth/logout` deletes the session. `GET /api/auth/me` returns `CurrentUser`.
- **Login rate limit:** 5 failures per username per 15 min, and 20 per IP per 15 min, then `429`. Use an in-process token bucket per worker.
  <br>`ponytail:` this is per-process; move it to a Postgres table if the API runs more than one replica.
- **CSRF:** the browser only talks to the Next BFF (same origin) and the cookie is `SameSite=Lax`. In addition, every mutating request must carry the header `X-DocuHive-CSRF: 1` (the BFF adds it, and a cross-site form cannot). Return `403` if it is missing. Bearer-token requests are exempt.

### API tokens (scripts, iOS Shortcuts, CAP-04)
- `POST /api/tokens {name, scopes}` returns the token **once**: `dh_<8-char prefix>_<32 random bytes b64url>`. The DB stores `prefix` + `sha256`.
- Scopes:

  | Scope | Allows |
  |-------|--------|
  | `upload` | only `POST /api/upload` |
  | `read` | GET documents and search |
  | `write` | read plus metadata edits |
  | `admin` | everything |

- `GET /api/tokens` (your own tokens), `DELETE /api/tokens/{id}` (revoke). `last_used_at` is updated at most once per minute.

### `current_user` dependency
1. Use the Bearer token if present, otherwise the `dh_session` cookie, otherwise `401`.
2. Check the token's scope against a route-level requirement: `Depends(scope("write"))`.
3. Dev bypass as in contracts §2.6. **Startup check:** `AUTH_DISABLED` with `ENV != dev` exits with an error.

### Permissions — `docuhive/auth/permissions.py`
- `visible_docs(user)` and `visible_docs_incl_trash(user)` exactly as in contracts §2.6. They are the **only** place this rule exists. Every documents query in OA code uses them, and the search code applies them in both lists.
- Write permission: only the **owner** may edit, trash or purge. A shared document is visible to everyone, but only the owner can edit it.
  <br>`ponytail:` household-level edit rights come later if wanted.
- `documents.get_for_user` is implemented here (raises `NotFound` both for missing documents and for ones the user can't see; never `403`, so existence doesn't leak).
- Tests: a matrix of owner/other/admin × private/shared/trashed for get, list, search, edit and download.

## 4.2 REST API — OA routers

All endpoints follow the conventions in contracts §6. Pydantic response models are defined in `api/schemas.py`, and they reuse `contracts` models where possible.

### Documents
| Method & path | Notes |
|---------------|-------|
| `GET /api/documents` | filters (all `SearchFilters` fields as query params, repeated keys for lists) + `status`, `sort=added_at|document_date|title` (`-` prefix = desc), cursor pagination. Returns `DocumentSummary` (id, title, date, category, type, correspondent, tags, status, thumb_url) |
| `GET /api/documents/{id}` | `DocumentView` + `notes` + `audit` (last 20) |
| `PATCH /api/documents/{id}` | body = `MetadataPatch` + optional `shared`. Calls `apply_metadata(actor="user:<id>")` |
| `POST /api/documents/bulk` | `{ids: [...], patch: MetadataPatch}` → max 500 ids. One job per 50 ids, returns the job ids |
| `POST /api/documents/{id}/trash` · `/restore` | soft delete / restore, emits events |
| `DELETE /api/documents/{id}?purge=true` | admin + owner only, needs `confirm=<id>`. Deletes the vault folder (moves it to `vault/_system/purged/<id>/` first, then deletes after 7 days) |
| `GET /api/documents/{id}/original` · `/archive` · `/thumb` | streams from the vault with the right `Content-Type`. `Content-Disposition: inline` for archive/thumb and `attachment` for original (`?inline=1` allowed for PDFs). `ETag` = sha256. Supports `Range` (FastAPI `FileResponse` handles it) |
| `GET/POST /api/documents/{id}/notes`, `DELETE /api/documents/{id}/notes/{note_id}` | notes go into `meta.json` too |

### Upload
`POST /api/upload` (multipart: `files[]`, optional `combine`, `shared`, `source=upload|mobile|api`):
1. Stream the files to `incoming_dir()`, enforcing `MAX_UPLOAD_MB` while streaming.
2. Call `ingest.submit`, and return `IngestResult` (`202`).
3. `source=api` is forced for Bearer tokens.

### Vocabulary
- `GET /api/vocabulary/tags` and `/correspondents`, with `?q=` (trigram) and usage counts.
- `PATCH` to rename, and `POST .../merge {source_ids, target_id}`.
- **Categories and document types are not here.** They come from CL's `/api/taxonomy`.

### System
| Method & path | Notes |
|---------------|-------|
| `GET /api/system/health` | public: `{status, version, db, vault}` |
| `GET /api/system/vault` | `VaultStatus` + free space (`shutil.disk_usage`) |
| `GET /api/system/quarantine` | quarantined documents with reason and size |
| `POST /api/system/quarantine/{id}/retry` · `/discard` | discard moves the staging files to `STAGING_DIR/_discarded/` (deleted after 30 days) |
| `GET /api/system/jobs`, `POST /api/system/jobs/{id}/retry` | from OA-M2 |
| `GET /api/system/stats` | counts by status, documents per month (last 12), staging size; used by the dashboard |

### Users (admin)
`GET/POST /api/users`, `PATCH /api/users/{id}` (role, disabled, password reset).

## 4.3 Search — `docuhive/search/`

### Full-text (`fts.py`)
- **Query parsing:** `websearch_to_tsquery(cfg, q)` for each configured FTS config (from the taxonomy `languages` via the language map, plus `dh_simple`), ORed: `q_de || q_en || q_simple`.
- **Ranking:** `ts_rank_cd(content_tsv, query, 32)` (normalised by document length).
- **Snippet:** `ts_headline(fts_config, content, query, 'StartSel=\u0002, StopSel=\u0003, MaxFragments=2, MaxWords=25, MinWords=8')`. Computed only for the final page of hits (it is expensive).
- **Typo fallback:** if FTS returns fewer than 5 hits, union with `title % :q OR correspondents.name % :q` (pg_trgm similarity ≥ 0.3), ranked below the FTS hits.
- **Filters:** a single builder, `filters_sql(SearchFilters)`, shared with `GET /api/documents` and `iter_ids`. Tag filters are AND (a document must have all the selected tags); the other lists are OR within a field.

### Hybrid (`hybrid.py`)
Implements contracts §2.7:
1. Get the FTS top 50 (ids + rank).
2. If semantic is registered and `mode != "fts"`, call `fn(user, q, filters, 50)`.
3. RRF: `score = Σ 1/(60 + rank)`.
4. Take the top `limit` and attach snippets: the FTS headline if present, otherwise the semantic chunk text truncated to 300 chars.
5. `mode="semantic"` with no fn registered → `400 semantic_unavailable`.

`GET /api/search?q=&mode=&limit=&<filters>` returns `{items: SearchHit + DocumentSummary, semantic_available: bool}`.

### Performance target (NFR-04): under 500 ms at 20k docs
- `docuhive dev seed --docs 20000` generates synthetic documents (random German/English text from a word list, random metadata) directly in the DB, without the vault. It is for benchmarking only.
- Benchmark script `tests/perf/search_bench.py` with 50 queries, reporting p50/p95. Tune with `EXPLAIN ANALYZE` (GIN index, avoiding `ts_headline` on many rows).

## 4.4 Setup status, unlock, document scope, learning
- **`GET /api/system/setup-status`** → `list[SetupCheck]` ([`guided-experience` skill](../../.agents/skills/guided-experience/SKILL.md)):
  - `vault` (mounted + initialised, required)
  - `security.admin_password` (changed from bootstrap, required)
  - `backup` (configured + last success < 48 h)
  - `capture.https` (`PUBLIC_URL` is https, so the camera works)
  - `capture.consume` (the folder exists, optional)
- **`unlock_fields`** in `PATCH /api/documents/{id}` (contracts §2.5, rule 6).
- **Field sources:** `GET /api/documents/{id}` adds `field_sources: {field: "ai" | "user" | null}`, computed from `manual_fields` and the `ai_provenance` keys, plus each AI field's `ai_run_id`. These drive the provenance badges ([`document-editing` skill](../../.agents/skills/document-editing/SKILL.md)).
- **Scope by documents:** `SearchFilters.document_ids` is supported in `filters_sql`, so `/documents?ids=…` and "Ask about this document" work.
- **Learning:**
  - Note `docs/learn/09-hybrid-search.md` + `examples/learn/09_hybrid_search.py` (FTS + a fake semantic list + RRF)
  - Note `docs/learn/12-pipelines-and-jobs.md` + `examples/learn/12_job_queue.py`

  Follow the [`learning-showcase` skill](../../.agents/skills/learning-showcase/SKILL.md).

## 4.5 Tests
- Auth:
  - login, logout, wrong password, rate limit
  - session expiry and sliding
  - token scopes
  - CSRF header required
  - `AUTH_DISABLED` refused in prod
- Permission matrix (§4.1).
- Upload:
  - size limit while streaming
  - combine validation
  - duplicate response
  - a Bearer token with only the `upload` scope cannot list documents
- Search:
  - German stemming ("Rechnungen" finds "Rechnung")
  - unaccent ("Muller" finds "Müller")
  - typo fallback ("Stadwerke" finds "Stadtwerke")
  - filter combinations
  - RRF ordering with a fake semantic fn
  - private docs of another user never appear in either list
- Contract tests for `auth` and `search` against the real implementation.

## Acceptance
- An OpenAPI schema is exported, and `make gen-api` produces types without errors.
- The permission matrix test is green. The search bench meets p95 < 500 ms on the dev laptop at 20k docs.
- With `docuhive.ai` absent, everything works (FTS-only search, events waiting as "no handler").
- **I5 marked done** in `STATUS.md`.

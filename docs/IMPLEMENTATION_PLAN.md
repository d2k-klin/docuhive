# DocuHive — Implementation Plan

Status: draft v0.3 · 2026-11-03 · own-core design · companion to [REQUIREMENTS.md](REQUIREMENTS.md)

## 1. Architecture

```
 Gmail API ──┐        PWA capture / web upload / API tokens        Next.js web (apps/web)
 MS Graph ───┤                         │                             login · docs · review
 IMAP ───────┤                         │                             search · ask · capture
             ▼                         ▼                                    │ BFF
      ┌──────────────────────── DocuHive (Python, services/docuhive) ───────▼───────────┐
      │  api (FastAPI): auth, documents, search, chat (SSE), uploads, OAuth callbacks    │
      │  worker:  ingest ─► ocr ─► vault write ─► classify/extract ─► embed              │
      │           mail sync/backfill · consume-folder poller · library view · backups    │
      │  agents:  Strands SDK → router → Ollama | Anthropic | OpenAI | Bedrock | LiteLLM │
      └──────┬──────────────────────┬───────────────────────┬──────────────────────────┘
             │ SQL                  │ HTTP                  │ subprocess
   Postgres 16 + pgvector     Gotenberg (office,       OCRmyPDF + Tesseract
   (metadata, FTS, vectors,   .eml, HTML → PDF)        (+ Ghostscript, unpaper)
    jobs, audit)                                             │
             │ host SSD: DB, staging/, models                │
             └───────────────────── NFS/SMB ─────────────────▼
                            WD My Cloud EX2 Ultra
              vault/<YYYY>/<doc_id>/{original.*, archive.pdf, meta.json, thumb.webp}
              library/ (generated view) · consume/ · _system/ (DB dumps)
```

**Design rules**
- **The vault is the source of truth, and Postgres is the index.** Every metadata write goes to the DB and `meta.json` in the same job. `docuhive vault rebuild` proves the DB can be recreated.
- One Python package with two entrypoints (`docuhive api`, `docuhive worker`). The job queue is a Postgres table polled with `FOR UPDATE SKIP LOCKED`, with no Celery or Redis.
  <br>`ponytail:` this ceiling is around 100k jobs/day; move to Valkey + RQ if that is ever hit.
- OCR, Gotenberg and AI calls run only in the worker. The API stays responsive.
- The Next.js app talks only to the DocuHive API (BFF pattern) and holds no business logic.
- Permissions live in a single SQL helper (`visible_docs(user)`), used by every query, including vector search and agent tools.

## 2. Tech stack

| Layer | Choice | Licence notes |
|-------|--------|---------------|
| OCR | OCRmyPDF (MPL-2.0) + Tesseract (Apache-2.0), with `deu`+`eng` traineddata | Ghostscript (AGPL) and unpaper (GPL) are called by OCRmyPDF as subprocesses only |
| Conversion | Gotenberg 8 container (MIT): office, `.eml`, HTML → PDF; `img2pdf` (LGPL) for images; `pillow-heif` for HEIC | separate container / library use |
| PDF utils | `pypdfium2` (Apache/BSD) for text, page count and thumbnails; `pikepdf` (MPL-2.0) for encryption checks | avoid PyMuPDF (AGPL) |
| Python | 3.12, `uv`, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, psycopg 3, httpx, argon2-cffi | |
| Search | Postgres FTS (`tsvector`, `websearch_to_tsquery`, `unaccent`), `pg_trgm`, `pgvector` HNSW | |
| Agents | `strands-agents` with the `ollama`, `anthropic`, `openai` and `litellm` extras; Bedrock via boto3 | |
| Embeddings | Ollama `bge-m3` (multilingual) by default, or provider embeddings | |
| Mail | Gmail REST via httpx + google-auth, Microsoft Graph via httpx + `msal`, IMAP via stdlib `imaplib` | |
| Web | Next.js 15 (App Router, TS), Tailwind, shadcn/ui, PWA manifest + service worker; native `<iframe>` PDF preview (pdf.js later for hit highlighting) | |
| Infra | Docker Compose, Tailscale, restic, GitHub Actions, `pip-licenses`/`license-checker` in CI | |

## 3. Repository layout

```
docuhive/
├─ apps/web/                     Next.js app
├─ services/docuhive/            Python package (+ Dockerfile with tesseract, ocrmypdf, ghostscript)
│  ├─ src/docuhive/
│  │  ├─ api/                    routers: auth, documents, search, chat, upload, sources, admin
│  │  ├─ worker/                 job loop, scheduler, consume-folder poller
│  │  ├─ ingest/                 stage.py, convert.py, ocr.py, text.py, thumbs.py, pipeline.py
│  │  ├─ vault/                  layout, atomic writes, meta.json schema + migrations, rebuild, library view
│  │  ├─ search/                 fts.py, semantic.py, hybrid.py
│  │  ├─ mail/                   gmail.py, graph.py, imap.py, prefilter.py
│  │  ├─ ai/                     router.py, budgets.py, privacy.py
│  │  ├─ agents/                 base.py (harness), triage.py, classify.py, extract.py, ask.py, tools/
│  │  ├─ auth/                   users, sessions, tokens, permissions
│  │  ├─ config/                 settings + overlay loader
│  │  └─ db/                     models, alembic migrations
│  └─ tests/
├─ config/defaults/              taxonomy.yaml, prompts/*.md, mail-rules.yaml, routing.yaml
├─ evals/                        harness CLI, synthetic sample set, scorers (ocr, classify, ask), baselines/
├─ examples/learn/               runnable learning examples, one concept each (FakeModel by default)
├─ deploy/
│  ├─ compose.yml                web, api, worker, postgres, gotenberg
│  ├─ compose.local.yml          + ollama (or host Ollama), local vault dir
│  ├─ compose.cloud.yml          no ollama, block-volume vault, Caddy or Tailscale
│  └─ scripts/                   backup.sh, restore.md, nas-setup.md
├─ overlay/  → (gitignored symlink to private repo)
├─ docs/                         README index, setup/, learn/ (learning path), decisions/, shared/, Developer-OA/, Developer-CL/
├─ .agents/skills/               canonical project skills (UI, repo structure, harness, learning, guidance, pipeline, editing, chat)
├─ .claude/skills/               thin pointers to .agents/skills for Claude Code
├─ .github/                      CODEOWNERS, PR/issue templates, dependabot, workflows (+ workflows/README.md)
├─ Makefile                      every command CI runs
├─ README · CHANGELOG · CONTRIBUTING · CODE_OF_CONDUCT · SECURITY · LICENSE
├─ AGENTS.md / CLAUDE.md         dev-harness instructions for coding agents
└─ .env.example
```

## 4. Public core vs private overlay

The private repo `docuhive-local` (or any path) is set via `DOCUHIVE_OVERLAY_DIR`:

```
docuhive-local/
├─ taxonomy.yaml          your categories, types, tags, fact schemas
├─ prompts/               prompt overrides (same filenames as defaults)
├─ mail-rules.yaml        sender allow/deny, labels, account scopes
├─ routing.yaml           provider/model per task, privacy rules, budgets
├─ plugins/               Python package, registered via entry point group `docuhive.plugins`
├─ evals/golden/          real documents + expected labels (never public)
└─ compose.override.yml   host-specific mounts, ports, extra services
```

- Loader order: `config/defaults/*`, then deep-merged with `overlay/*`, then env vars. Lists such as categories are **replaced**, not merged, so your taxonomy fully wins.
- Plugins are loaded with `importlib.metadata.entry_points(group="docuhive.plugins")`. Hooks: `prefilter(msg)`, `after_ingest(doc)`, `after_classify(doc, result)`, `extra_tools()`, `extractors()`.
- `.gitignore` covers `overlay/`, `.env*` (except `.env.example`) and `*.local.*`. A CI check fails if `overlay/` or secrets are tracked (gitleaks).

## 5. Vault format

```
vault/
├─ 2026/
│  └─ 01JC9Z4K7R…/                 doc_id = ULID (time-sortable, unique)
│     ├─ original.pdf              bytes as received, never touched again
│     ├─ archive.pdf               PDF/A with text layer
│     ├─ thumb.webp
│     └─ meta.json
├─ library/                        generated view (hardlinks on NFS), safe to delete
├─ consume/                        scanner drop folder (polled)
└─ _system/                        nightly DB dumps, vault format version
```

Example `meta.json`:

```json
{
  "schema": 1,
  "id": "01JC9Z4K7R...",
  "sha256": "…",
  "original_filename": "Rechnung_2026_11.pdf",
  "mime": "application/pdf",
  "pages": 2,
  "added_at": "2026-11-03T21:10:00Z",
  "owner": "davor",
  "shared": true,
  "source": {
    "kind": "email",
    "account": "gmail:…",
    "message_id": "…",
    "from": "…",
    "subject": "…",
    "received_at": "…"
  },
  "title": "Electricity invoice – November 2026",
  "document_date": "2026-11-01",
  "language": "de",
  "category": "utilities/electricity",
  "document_type": "invoice",
  "correspondent": "Stadtwerke …",
  "tags": ["property"],
  "facts": {
    "amount": { "value": "84.20", "currency": "EUR" },
    "due_date": "2026-11-20",
    "invoice_no": "…"
  },
  "notes": [],
  "ai": { "classify": { "model": "ollama/qwen3:8b", "prompt": "classify@3", "confidence": 0.93, "at": "…" } },
  "manual_fields": ["title"],
  "deleted_at": null
}
```

Notes on the format:
- OCR text is not stored in `meta.json`, because `archive.pdf` holds it. A rebuild re-extracts it with pypdfium2.
- `manual_fields` protects user edits from re-classification (CLS-06).
- Writes go through `vault.write_json()` (temp file + fsync + rename in the same directory).

**Vault health (STO-05).**
1. The worker checks `vault/_system/VAULT_ID`, which must match the DB, before any vault write.
2. If the check fails, the vault-write jobs pause. Uploads still land in `staging/` on the SSD, and the UI shows a banner.
3. Once the vault is back, the paused jobs resume.

The vault is never created automatically inside an empty mount point.

## 6. Core flows

### 6.1 Ingest pipeline (all sources)
1. **Receive** (API upload, PWA, email worker, consume poller). Stream to `staging/<uuid>` on the SSD, compute SHA-256, and insert `documents(status=staged)`. Respond to the client right away.
2. **Dedupe**: if `(owner, sha256)` exists, mark the upload as a duplicate, link it to the existing doc, and stop.
3. **Detect type**: magic bytes, not the file extension.
4. **Convert**:
   - images (HEIC → JPEG) → `img2pdf`
   - office, `.eml` and HTML → Gotenberg `/forms/libreoffice/convert` or `/forms/chromium/convert/html`
   - PDF as is
   - encrypted PDF → try an empty password with pikepdf, otherwise quarantine
5. **OCR**: `ocrmypdf --output-type pdfa --skip-text --rotate-pages --deskew -l deu+eng --jobs 2 in.pdf archive.pdf`. Text pages are skipped, but scanned pages within the same PDF are still OCR'd. There is a per-page timeout, and the job retries without `--deskew` on failure.
6. **Extract text** (pypdfium2) and thumbnail (page 1 → webp).
7. **Vault write**: copy the original and archive with atomic writes, verify their checksums, and write `meta.json`. Commit the DB row (`status=stored`, content, `content_tsv`). Only then delete the staging file.
8. Enqueue **classify** → **extract** → **embed**.
9. On any failure, set `status=quarantined` with a reason. The staged file stays, with a "Retry" action in the UI.

### 6.2 Email → ingest
1. **Sync** (every 15 min per account) via the provider cursor. **Backfill** jobs instead page through a date-range query:
   Gmail `after:YYYY/MM/DD before:… has:attachment`, Graph `$filter=receivedDateTime ge … and hasAttachments eq true`, IMAP `SEARCH SINCE … BEFORE …`. The page token is stored on the job, so it resumes after a crash.
2. **Ledger**: upsert `mail_messages(account_id, provider_msg_id)` and skip any message already processed.
3. **Pre-filter** (no AI): mime types, size, allow/deny, promo signals. Most mail stops here.
4. **AI triage** (cheap model, structured output `{archive, reason, confidence, doc_hint}`). Input: sender, subject, a body snippet of 2 KB, and attachment names and types. Full attachments are never sent to the AI at this stage.
5. Accepted attachments, and optionally the body rendered as PDF, go into §6.1 with `source.kind=email` provenance.

### 6.3 Mobile capture (PWA)
- The `/capture` page uses `<input type="file" accept="image/*" capture="environment" multiple>`. Thumbnails can be reordered and deleted.
- Images are downscaled on the device to 2400 px on the long edge as JPEG q85 via canvas, then sent to `POST /api/upload?combine=true`. The pipeline merges them into one PDF.
- If the network is flaky, the service worker queues uploads in IndexedDB and retries them.
- The page is served over HTTPS via `tailscale serve`, because camera access requires a secure context.

### 6.4 Classify → extract → index
1. Load the content (truncated to the context budget, keeping the first and last pages) plus the vocabulary (taxonomy, correspondents, tags).
2. **Privacy gate**: restricted category/tag hints or `local_only` → local model.
3. **Classify agent** (Strands `structured_output` into a Pydantic model):
   `{title, category, document_type, correspondent, tags[], document_date, language, confidence{field}, proposed_new_terms[]}`.
   Unknown labels are rejected by validation, with one retry carrying an error hint.
4. **Extract** with the per-type fact schema from the taxonomy. Values are validated (date parse, ISO 4217 currency, amount > 0, IBAN mod-97).
5. **Apply**:
   - Fields above the threshold (default 0.8) that are not in `manual_fields` are written to the DB and `meta.json`.
   - Anything else adds the document to the review queue.
   - The FTS language config is updated from the detected `language`.
6. **Embed**: chunks of ~800 tokens with overlap → `doc_chunks`.
7. Log an `ai_runs` row (task, provider, model, prompt version, tokens, cost, latency, raw output).

### 6.5 Search
- **Full-text**: a `content_tsv` column is built from `setweight(title,'A') || setweight(correspondent,'B') || setweight(content,'C')` using the document's `fts_config` (`german`/`english`/`simple`), wrapped in `unaccent`.
  The query is `websearch_to_tsquery` in each configured language, ORed together. Snippets come from `ts_headline`. A `pg_trgm` fallback handles typos in titles and correspondents.
- **Semantic**: the query is embedded, then a pgvector cosine search runs over `doc_chunks` joined to `visible_docs(user)` and the filters.
- **Hybrid**: reciprocal rank fusion of the two result lists in one SQL statement (`k=60`).
  <br>`ponytail:` RRF without tuning; add weights if the eval shows a need.

### 6.6 Ask / analyse
A Strands agent (`agents/ask.py`) streams over SSE. Its tools all run through `visible_docs(user)`:

| Tool | Backing |
|------|---------|
| `search(query, filters, mode)` | hybrid search (§6.5) |
| `get_document(id, max_chars)` | DB content + metadata |
| `query_facts(doc_type, field, group_by, date_range, agg)` | SQL over `doc_facts`, returning rows + total (no LLM math) |
| `list_vocabulary()` | taxonomy + correspondents |

The system prompt requires citations as `[doc:<id>]`, which the UI renders as preview links.
Saved analyses store `{prompt, filters, provider}` and can be re-run.

## 7. Data model (Postgres)

| Table | Key columns |
|-------|-------------|
| `users` | id, username, pw_hash (argon2), role, created_at |
| `sessions` / `api_tokens` | user_id, token_hash, scopes, expires_at, last_used |
| `documents` | id (ULID), owner_id, shared, sha256, mime, pages, vault_path, title, document_date, language, fts_config, category, document_type, correspondent_id, content, content_tsv (generated), status, quarantine_reason, manual_fields[], added_at, deleted_at; UNIQUE(owner_id, sha256) |
| `tags` / `document_tags` / `correspondents` | name, slug, merged_into |
| `doc_facts` | document_id, field, value_num, value_date, value_text, currency, confidence |
| `doc_sources` | document_id, kind, account_id, message_id, from, subject, received_at |
| `doc_chunks` | document_id, chunk_no, text, embedding vector(N), embed_model |
| `notes` | document_id, user_id, body, created_at |
| `audit_log` | user_id/agent, document_id, action, before jsonb, after jsonb, at |
| `mail_accounts` | provider, address, enc_refresh_token, cursor, enabled |
| `mail_messages` / `mail_attachments` | provider_msg_id, status, triage_reason, triage_confidence, sha256, document_id |
| `backfills` | account_id, date_from, date_to, page_token, scanned, imported, status |
| `jobs` | kind, payload jsonb, status, attempts, run_after, locked_at, error |
| `ai_runs` | task, document_id, provider, model, prompt_version, tokens_in/out, cost, latency_ms, output jsonb |
| `analyses` | user_id, name, prompt, filters, provider, last_result |

The vault ID and schema version live in `settings`. Tokens are encrypted with Fernet, keyed by `DOCUHIVE_SECRET_KEY`.

## 8. AI provider layer & harness

`ai/router.py` resolves `(task) → Strands Model` from `routing.yaml`:

```yaml
defaults: { provider: ollama, model: qwen3:8b }
tasks:
  triage:   { provider: ollama,    model: qwen3:4b }
  classify: { provider: ollama,    model: qwen3:8b }
  extract:  { provider: ollama,    model: qwen3:8b }
  embed:    { provider: ollama,    model: bge-m3 }
  chat:     { provider: anthropic, model: claude-sonnet-5-5, fallback: ollama/qwen3:8b }
privacy:
  local_only: false
  restricted: { categories: [medical, identity], tags: [private] }   # → forced local
budgets: { anthropic: { monthly_usd: 10 }, openai: { monthly_usd: 5 } }
```

| Provider | Strands model class | Notes |
|----------|--------------------|-------|
| Ollama | `OllamaModel` | default; host Ollama on macOS for Metal GPU |
| Anthropic | `AnthropicModel` | API key |
| OpenAI / compatible | `OpenAIModel` (custom `base_url`) | also LM Studio, vLLM, OpenRouter |
| Bedrock | `BedrockModel` | AWS profile/role; natural choice in AWS cloud |
| GitHub Copilot | `LiteLLMModel` (`github_copilot/...`) | **experimental**, may break |

**Agent harness** (`agents/base.py`) wraps every agent run with:
- task routing
- privacy gate
- budget check, which pauses backfill jobs when a cap is hit
- timeout and retry
- structured-output validation
- `ai_runs` logging

Prompts are versioned files, and the prompt version is stored per run.

**Eval harness** (`evals/`):
```
docuhive eval ocr      --set overlay/evals/golden          # CER/WER vs. ground-truth text, time/page
docuhive eval classify --set overlay/evals/golden --route classify=ollama/qwen3:8b
docuhive eval search   --set overlay/evals/search.yaml     # recall@10 for known queries
docuhive eval ask      --set overlay/evals/qa.yaml
```
- It reports per-field accuracy, unknown-label rate, latency and cost per 100 docs, written as markdown and JSON.
- A synthetic set in the public repo runs in CI. The real golden set (~100 labelled docs from your archive) stays in the overlay.
- Rule: auto-apply for a model is enabled only after it passes the target on the golden set (NFR-09).

**Dev harness**: `AGENTS.md`/`CLAUDE.md` hold build, test and lint commands and conventions, so Claude Code, Copilot or another coding agent can work on the repo consistently.

## 9. Deployment profiles

### 9.1 Always-on home host (recommended)
- **Host**: Linux mini PC. 16 GB if cloud AI does the heavy lifting; 32 GB for local 7–8B models. 512 GB NVMe. OCR is CPU-bound, so 4+ cores helps. An existing always-on Mac also works: run Ollama natively for the GPU, Docker via OrbStack, and mount the NAS through macOS.
- **NAS**: NFS export (preferred, hardlinks work for the library view) or SMB, mounted with systemd `automount`. The compose file bind-mounts the vault path, and the vault-ID check (§5) protects against an unmounted directory.
- **WD settings**: firmware OS 5 latest, cloud access/UPnP off, a dedicated `docuhive` user/share, and RAID 1 (back up before any firmware change).
- **Access**: Tailscale on the host. Services bind to the Tailscale IP or LAN only. `tailscale serve` provides HTTPS.
- **Backups** (`backup.sh`, nightly via systemd timer):
  - `pg_dump` → `vault/_system/`
  - `restic` of the whole vault to a USB disk and/or B2/S3
  - Monthly restore drill: an empty DB, `vault rebuild`, then a check of document counts and search.

### 9.2 Laptop/dev
`docker compose -f deploy/compose.yml -f deploy/compose.local.yml up` with `./data/vault`. Use it for development and trying things out.

### 9.3 Cloud (if someone wants it hosted)
**Preferred: one small VM running the same compose file** (`compose.cloud.yml`). Use Hetzner, Lightsail or EC2 with 4 vCPU and 8–16 GB RAM.
- **No local LLM**. Route AI tasks to Bedrock, Anthropic or OpenAI. Restricted documents get no AI, or a small CPU model.
- **Storage**: the vault on an attached block volume, with restic nightly to S3/B2. **The WD stays the permanent home copy**: a home device pulls the vault over Tailscale with `rclone`/`restic` on a schedule. Because the vault is self-describing, the home copy is complete without the cloud DB.
- **Access**: Tailscale-only (best), or Caddy with TLS, rate limiting and fail2ban if public access is required.

**Scale-out option (multi-user, not for personal use)**: AWS ECS Fargate (api, worker, web), RDS Postgres with pgvector, EFS for the vault (or an S3 vault backend, which is not planned), Bedrock, ALB. It costs more and has more moving parts; consider it only if this becomes a hosted product.

## 10. Phases

Each phase ends in something usable. Estimates assume part-time evenings, about 18 weeks in total.

### Phase 0 — Foundations + OCR spike (weeks 1–2) · **go/no-go gate**
- Repo skeleton (§3), Apache-2.0 licence, `AGENTS.md`, `.env.example`, gitleaks, a licence check, and CI running ruff, pytest, eslint, tsc and the synthetic evals.
- Overlay loader, with a test.
- **Spike**: run the ingest steps (§6.1, steps 3–6) as a CLI over **50 of your real documents**: born-digital PDFs, scans, phone photos, office files, emails, German and English. Measure success rate, OCR quality (spot check plus CER on 10 hand-transcribed pages), and seconds per page on the target host.
- **Gate**: at least 95% ingest without manual intervention, readable OCR on scans and photos, and under 10 s per page. If the gate fails, fall back to the Paperless-based plan (commit `2f38128`).

### Phase 1 — Core archive (weeks 3–5)
- DB models + Alembic, job queue, worker loop.
- Ingest pipeline, vault writer, `meta.json`, quarantine, dedupe.
- Auth (users, sessions, API tokens) and the permission helper.
- API: upload, list, get, download, update metadata, FTS search.
- Web: login, upload, document list with filters, detail with preview, metadata edit, quarantine view.
- `vault rebuild`, backups, vault-health pause/resume.
- **Exit**:
  - An upload lands on the NAS, OCR'd, and is searchable in the web UI.
  - Unplugging the NAS pauses vault writes, keeps uploads in staging, and resumes when it is back.
  - Dropping the DB and running `vault rebuild` restores all documents and metadata.

### Phase 2 — Mobile + consume folder (week 6)
- PWA manifest, service worker with an upload queue, `/capture` with multiple pages and reordering, and Tailscale HTTPS.
- Consume-folder poller (stable-size check before picking up a file).
- **Exit**: a 3-page letter photographed on the phone away from home becomes one searchable PDF in the vault.

### Phase 3 — AI layer + auto-classification (weeks 7–9)
- Provider router (Ollama, Anthropic, OpenAI, Bedrock, LiteLLM), agent harness, `ai_runs`, budgets, privacy gate.
- Default taxonomy plus your overlay taxonomy. Classify and extract agents with validation. Review queue UI (accept, fix or reject with one click). Vocabulary management and merging.
- Eval harness, plus a golden set of about 100 of your docs.
- **Exit**:
  - New docs are auto-classified within 5 min.
  - The eval report compares at least two models.
  - Auto-apply is enabled only once a model meets ≥ 90% on category and type.
  - Restricted documents never produce a cloud `ai_runs` row (test).

### Phase 4 — Email ingestion (weeks 10–12)
- OAuth flows (Google Cloud project, Azure app registration for personal accounts), with encrypted tokens.
- Gmail, Graph and IMAP connectors. Pre-filter. Triage. Provenance. Ledger and dedupe. Incremental sync. Backfills with progress and resume. Sources UI.
- **Exit**:
  - A one-year backfill on Gmail and Outlook completes.
  - Re-running it imports 0 new items.
  - Killing the worker mid-backfill and restarting it resumes cleanly.
  - Triage decisions are reviewable.

### Phase 5 — Semantic + hybrid search, Ask (weeks 13–15)
- Chunking, embeddings, HNSW index, embedding backfill. Hybrid search. "Similar documents".
- The `doc_facts` aggregation tool, the Ask agent, SSE chat UI with citations, and saved analyses.
- Search and Q&A eval sets.
- **Exit**:
  - "How much did I spend on electricity in 2025?" returns a total computed by `query_facts`, with every invoice cited.
  - Search recall@10 meets its target.
  - User A's chat can never cite user B's private documents (test).

### Phase 6 — Hardening + cloud profile (weeks 16–18)
- Bulk edit, trash/restore, audit log view, and the library view generator.
- Notifications plugin (ntfy). Reminders for due and renewal dates.
- `compose.cloud.yml` plus the cloud-to-NAS pull sync, and docs.
- Security pass: dependency and licence audit, upload fuzzing (malformed PDFs and zip bombs into an isolated converter), CSRF/session review, and rate limits.
- **Exit**: the cloud profile deploys from the docs alone, the security checklist is done, and a full restore drill from restic passes.

### Later / backlog
- Client-side edge detection/cropping in the PWA.
- Password entry for encrypted PDFs.
- Page split and merge.
- Vision-LLM OCR for poor scans.
- Passkeys/OIDC.
- Taxonomy editor in the UI.
- Telegram/WhatsApp forward-to-archive, and an email forward-to-archive address.
- An S3 vault backend.
- A Paperless-ngx importer, for others migrating.

## 11. Testing strategy

- **Unit**: vault atomic writes and the `meta.json` schema and migrations, type detection, dedupe, prefilter rules, taxonomy validation, fact validators, overlay merge, router, privacy gate, permission helper, RRF (pytest). Web: component tests only where there is logic.
- **Integration**: compose test stack (Postgres, Gotenberg, the worker image with Tesseract) over a fixture set of tricky files (rotated scans, mixed text/scan PDFs, encrypted, HEIC, docx, `.eml`). Recorded Gmail/Graph fixtures. A fake LLM provider with canned structured output.
- **Evals**: the synthetic set runs in CI; the golden set runs locally before changing a model, prompt or OCR setting.
- **Ops drills**: vault rebuild, NAS-down, provider-down (falls back or queues), and restore from restic.

## 12. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| OCR and format edge cases | Phase 0 spike with a go/no-go gate, quarantine-and-retry, a fixture corpus in CI, and the Paperless fallback plan. |
| More to build than with Paperless | A strict v1 scope (§7 of the requirements), libraries for the hard parts, phases that are each usable. |
| WD EX2 Ultra end of support (Dec 2026) | LAN-only, no WD cloud. The vault is a plain folder, so swap NAS/disk later. Independent restic copy. |
| NAS unavailable | Vault-ID check, staging buffer, pause/resume, alerting. |
| DB loss or corruption | The vault is the truth, `vault rebuild`, nightly dumps. |
| Malicious or malformed uploads | Type sniffing, size limits, conversion in the Gotenberg container, OCR in the worker with timeouts, non-root containers. |
| Wrong amounts/dates from LLM | Typed validation, confidence threshold, review queue, numbers only via `query_facts`. |
| Sensitive docs sent to cloud AI | Privacy gate before every call, local-only switch, restricted categories/tags, audit in `ai_runs`. |
| Gmail testing-mode tokens expire after 7 days | Publish the personal GCP app to production (unverified) or use IMAP with an app password. |
| Cost spike on backfill with cloud AI | Default local for triage/classify, monthly budgets, backfill auto-pause. |
| AGPL contamination | Licence check in CI, AGPL/GPL tools only as subprocesses or containers. |

## 13. What you need (shopping/setup list)

1. **Always-on host**: an existing PC or Mac, or a mini PC (16 GB minimum, 32 GB recommended, 4+ cores, NVMe). Docker, Tailscale.
2. **WD EX2 Ultra**: updated to the latest OS 5, healthy drives, RAID 1, a `docuhive` share (NFS preferred), cloud features off.
3. **Second backup target**: a USB disk and/or a B2/S3 bucket.
4. **Accounts**:
   - Google Cloud project (Gmail API OAuth client)
   - Azure app registration (personal Microsoft accounts, `Mail.Read`, `offline_access`)
   - Optional API keys: Anthropic, OpenAI, AWS (Bedrock)
   - Tailscale (free personal)
5. **Phone**: any modern iOS/Android browser for the PWA.
6. **Private GitHub repo** `docuhive-local` for the overlay.
7. **50 sample documents** for the Phase 0 spike, and ~100 labelled ones for the golden set.

## 14. Work split, skills and UX surfaces

- **Two parallel tracks:** [docs/shared/README.md](shared/README.md) (the split), [docs/Developer-OA/](Developer-OA/README.md) and [docs/Developer-CL/](Developer-CL/README.md).
- **Binding conventions** live as project skills in [`.agents/skills/`](../.agents/skills/README.md): `docuhive-ui`, `repo-structure`, `strands-agent-harness`, `learning-showcase`, `guided-experience`, `document-pipeline`, `document-editing`, `document-chat`.
- **UX surfaces added in v0.3**, specified in the skills and scheduled in the track plans:
  - the `/setup` wizard and dashboard checklist (`SetupCheck`)
  - the `/dev/ui` kitchen sink and control-height test
  - the "How was this made?" run page
  - `docs/learn/` + `examples/learn/`
  - provenance badges, locks and undo on edits
  - the ⌘K palette and the "Ask about …" entry points


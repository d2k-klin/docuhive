# DocuHive — Implementation Plan

Status: draft v0.1 · 2026-11-03 · companion to [REQUIREMENTS.md](REQUIREMENTS.md)

## 1. Architecture

```
 Gmail API ──┐                                   ┌── Next.js web (apps/web)
 MS Graph ───┤                                   │     login · dashboard · review · search
 IMAP ───────┤                                   │     ask/chat · sources · capture PWA
             ▼                                   ▼
      ┌──────────────────────────── DocuHive (Python, services/docuhive) ───────────────┐
      │  api (FastAPI)            worker (same package, 2nd entrypoint)                 │
      │   • auth via Paperless     • mail sync + backfill   • classify + extract        │
      │   • chat/agents (SSE)      • triage (AI)            • embed / index             │
      │   • OAuth callbacks        • job queue = Postgres (SKIP LOCKED)                 │
      │  agents: Strands SDK → provider router → Ollama | Anthropic | OpenAI | Bedrock | │
      │                                          LiteLLM (Copilot, others)              │
      └───────────────┬──────────────────────────────────────────▲────────────────────┘
          REST (upload,│PATCH metadata, search)        webhook    │ "Document Added"
                       ▼                                          │
      ┌──────────── Paperless-ngx 3.1.x ─────────────────────────┴─┐   iOS/Android
      │ OCR (OCRmyPDF/Tesseract) · full-text · storage paths · UI   │◄── Paperless apps
      └──────┬────────────────────────────────┬────────────────────┘
             │ SSD (host)                     │ NFS/SMB
   Postgres 16 + pgvector, Valkey,      WD My Cloud EX2 Ultra
   Ollama models, indexes               /paperless/media  /consume  /backups
```

**Design rules**
- Paperless owns documents and metadata. DocuHive owns email state, AI runs, embeddings and chat. DocuHive never touches files on the NAS directly; everything goes through the Paperless API.
- One Python package with two entrypoints (`docuhive api`, `docuhive worker`). No Celery: a Postgres job table is enough at personal scale.
  <br>`ponytail:` this ceiling is around 100k jobs/day; move to Valkey + RQ if that is ever hit.
- One Postgres instance with two databases (`paperless`, `docuhive`). `pgvector` is used in `docuhive`.
- The Next.js app talks only to the DocuHive API (BFF pattern) and holds no business logic.

## 2. Tech stack

| Layer | Choice |
|-------|--------|
| Document system | Paperless-ngx 3.1.x (pinned image tag), Gotenberg + Tika (optional profile, for .eml/office) |
| Python | 3.12, `uv`, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, psycopg 3, httpx |
| Agents | `strands-agents` (+ `strands-agents[ollama,anthropic,openai,litellm]`), Bedrock via boto3 |
| Embeddings | Ollama `nomic-embed-text` / `bge-m3` (multilingual) by default, or provider embeddings |
| Vector store | pgvector (HNSW index) |
| Mail | Gmail REST via httpx + google-auth, Microsoft Graph via httpx + `msal`, IMAP via stdlib `imaplib` |
| Web | Next.js 15 (App Router, TS), Tailwind, shadcn/ui, PWA manifest + service worker |
| Infra | Docker Compose, Tailscale, restic, GitHub Actions |

## 3. Repository layout

```
docuhive/
├─ apps/web/                     Next.js app
├─ services/docuhive/            Python package
│  ├─ src/docuhive/
│  │  ├─ api/                    FastAPI routers (auth, docs, chat, sources, hooks, admin)
│  │  ├─ worker/                 job loop + scheduler
│  │  ├─ paperless/              typed API client
│  │  ├─ mail/                   gmail.py, graph.py, imap.py, prefilter.py
│  │  ├─ ai/                     router.py (providers), budgets.py, privacy.py
│  │  ├─ agents/                 triage.py, classify.py, extract.py, ask.py, tools/
│  │  ├─ index/                  chunking, embeddings, semantic search
│  │  ├─ config/                 settings + overlay loader
│  │  └─ db/                     models, alembic migrations
│  └─ tests/
├─ config/defaults/              taxonomy.yaml, prompts/*.md, mail-rules.yaml, routing.yaml
├─ evals/                        harness CLI, synthetic sample set, scorers
├─ deploy/
│  ├─ compose.yml                base stack
│  ├─ compose.local.yml          host Ollama, LAN/Tailscale
│  ├─ compose.cloud.yml          no Ollama, Caddy/Tailscale, cloud volume
│  └─ scripts/                   nas-check.sh, backup.sh, restore.md
├─ overlay/  → (gitignored symlink to private repo)
├─ docs/
├─ AGENTS.md / CLAUDE.md         dev-harness instructions for coding agents
└─ .env.example
```

## 4. Public core vs private overlay

The private repo `docuhive-local` (or any path) is set via `DOCUHIVE_OVERLAY_DIR`:

```
docuhive-local/
├─ taxonomy.yaml          your categories, types, tags, custom fields
├─ prompts/               prompt overrides (same filenames as defaults)
├─ mail-rules.yaml        sender allow/deny, labels, account scopes
├─ routing.yaml           provider/model per task, privacy rules, budgets
├─ plugins/               Python package, registered via entry point group `docuhive.plugins`
├─ evals/golden/          real documents + expected labels (never public)
└─ compose.override.yml   host-specific mounts, ports, extra services
```

- Loader order: `config/defaults/*`, then deep-merged with `overlay/*`, then env vars. Lists such as categories are **replaced**, not merged, so your taxonomy fully wins.
- Plugins are loaded with `importlib.metadata.entry_points(group="docuhive.plugins")`. Hooks: `prefilter(msg)`, `after_classify(doc, result)`, `extra_tools()`, `extractors()`.
- `.gitignore` covers `overlay/`, `.env*` (except `.env.example`) and `*.local.*`. A CI check fails if `overlay/` or secrets are tracked (gitleaks).
- Upstream updates: `git pull` the public repo. The overlay is untouched because it is a separate repo.

## 5. Core flows

### 5.1 Email → archive
1. **Sync** (worker, every 15 min per account). Fetch new message IDs via the provider cursor. Backfill jobs instead page through a date-range query:
   Gmail `after:YYYY/MM/DD before:… has:attachment`, Graph `$filter=receivedDateTime ge … and hasAttachments eq true`, IMAP `SEARCH SINCE … BEFORE …`.
2. **Ledger**: upsert into `mail_messages(account_id, provider_msg_id)`. Skip it if already processed. Backfill progress is a cursor/page token stored on the job, so it resumes after a crash.
3. **Pre-filter** (no AI): mime types, size, allow/deny, promo signals. Most mail stops here.
4. **AI triage** (cheap model, structured output `{archive: bool, reason, confidence, doc_hint}`). Input: sender, subject, a body snippet of 2 KB, and attachment names and types. It never sends full attachments to the AI at this stage.
5. **Import**: compute the attachment SHA-256 and skip it if it is in the ledger. Then `POST /api/documents/post_document/` with `title`, `created`, tag `src:email`, and custom fields `source_account`, `message_id`, `email_from`. Optionally, the body is rendered to PDF (the `.eml` route through Gotenberg).
6. Record the Paperless task id. Poll `/api/tasks/` for completion and map it to the `document_id`.

### 5.2 Mobile / scanner / web upload
- Paperless apps and the consume folder go straight into Paperless.
- The PWA `/capture` page uses `<input type="file" accept="image/*" capture multiple>`, then `POST /api/capture`. DocuHive merges the images into one PDF (`img2pdf`) when asked and uploads with tag `src:mobile`.
- All sources converge at Paperless's **Document Added workflow → Webhook action** → `POST /hooks/paperless` (shared secret header) → enqueue `classify(document_id)`.
  As a fallback, the worker polls `/api/documents/?added__gt=<last>` every 5 min in case a webhook is missed.

### 5.3 Classify → extract → index
1. Fetch the document's OCR `content` (truncated to the model's context window) plus the current vocabulary: taxonomy and existing Paperless tags, types and correspondents.
2. **Privacy gate**: if a tag or doc-hint matches a restricted rule, route to a local model only.
3. **Classify agent** (Strands, `structured_output` into a Pydantic model):
   `{title, category, document_type, correspondent, tags[], created_date, confidence{field: 0..1}, proposed_new_terms[]}`.
   Validation rejects any label not in the vocabulary and retries once with an error hint.
4. **Extract** with the per-type schema from the taxonomy (e.g. `invoice: amount: monetary, due_date: date, invoice_no: string`). Values are validated (date parse, currency code, amount > 0).
5. **Apply**: fields above the threshold (default 0.8) go to `PATCH /api/documents/{id}/`, setting the storage path from the category. Any field below the threshold is left as is, and the document gets tag `needs-review`.
6. **Index**: chunk the content (~800 tokens with overlap), embed it, and upsert `doc_chunks`. Mirror the extracted fields to the `doc_facts` table for analytics.
7. Log an `ai_runs` row: task, provider, model, prompt hash, tokens, cost, latency, raw output.

### 5.4 Ask / analyse
A Strands agent (`agents/ask.py`) streams over SSE to the web UI. Tools:

| Tool | Backing |
|------|---------|
| `search_fulltext(query, filters)` | Paperless `/api/documents/?query=` using **the user's token** |
| `search_semantic(query, filters, k)` | pgvector, post-filtered by verifying IDs through Paperless with the user's token |
| `get_document(id, max_chars)` | Paperless content + metadata |
| `query_facts(type, field, group_by, date_range, agg)` | SQL over `doc_facts`, returning rows + total (no LLM math) |
| `list_vocabulary()` | taxonomy |

The system prompt requires citations as `[doc:123]`. The UI renders them as links to the preview.
Saved analyses store `{prompt, filters, provider}` and can be re-run.

## 6. DocuHive data model (Postgres `docuhive` DB)

| Table | Key columns |
|-------|-------------|
| `users` | paperless_user_id, display_name (no passwords; Paperless is the identity provider) |
| `mail_accounts` | id, provider (gmail/graph/imap), address, enc_refresh_token, cursor, enabled, label_on_import |
| `mail_messages` | account_id, provider_msg_id, received_at, from, subject, status (skipped/rejected/imported/error), triage_reason, triage_confidence |
| `mail_attachments` | message_id, filename, sha256 UNIQUE, paperless_task_id, paperless_doc_id |
| `jobs` | id, kind, payload jsonb, status, attempts, run_after, locked_at, error |
| `backfills` | account_id, date_from, date_to, page_token, scanned, imported, status |
| `ai_runs` | task, document_id, provider, model, prompt_version, tokens_in/out, cost, latency_ms, output jsonb |
| `doc_chunks` | document_id, chunk_no, text, embedding vector(N), embed_model |
| `doc_facts` | document_id, doc_type, field, value_num, value_date, value_text, currency |
| `analyses` | user_id, name, prompt, filters, provider, last_result |

Tokens are encrypted with Fernet, keyed by `DOCUHIVE_SECRET_KEY`.

## 7. AI provider layer & harness

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
  restricted_tags: [private, medical, id-document]   # → forced local
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

Prompts are versioned files, and the prompt hash is stored per run.

**Eval harness** (`evals/`):
```
docuhive eval classify --set overlay/evals/golden --route classify=ollama/qwen3:8b
docuhive eval ask      --set overlay/evals/qa.yaml
```
- It reports per-field accuracy, unknown-label rate, latency and cost per 100 documents, written as markdown and JSON.
- A synthetic set in the public repo runs in CI. The real golden set (~100 labelled docs from your archive) stays in the overlay.
- Rule: auto-apply for a model is enabled only after it passes the target on the golden set (REQUIREMENTS NFR-09).

**Dev harness**: `AGENTS.md`/`CLAUDE.md` hold build, test and lint commands and conventions, so Claude Code, Copilot or another coding agent can work on the repo consistently.

## 8. Deployment profiles

### 8.1 Always-on home host (recommended)
- **Host**: Linux mini PC. 16 GB if cloud AI does the heavy lifting; 32 GB for local 7–8B models. 512 GB NVMe. An existing always-on Mac also works: run Ollama natively for the GPU, Docker via OrbStack, and mount the NAS through macOS.
- **NAS**: NFS export (preferred) or SMB, mounted via systemd `automount`. `deploy/scripts/nas-check.sh` verifies the sentinel file `/mnt/docuhive-nas/.docuhive-nas-ok`, and the Paperless container depends on a `nas-check` service, so it cannot start against an empty dir (STO-04).
- **WD settings**: firmware OS 5 latest, cloud access/UPnP off, a dedicated `paperless` user/share, and RAID 1 (back up before any firmware change).
- **Access**: Tailscale on the host. Paperless and DocuHive bind to the Tailscale IP or LAN only. `tailscale serve` provides HTTPS for the PWA, since camera capture needs a secure context.
- **Backups** (`backup.sh`, nightly via systemd timer):
  - `document_exporter` → NAS `/backups`
  - `pg_dump` of both DBs → NAS
  - `restic` of the export to a USB disk and/or B2/S3
  - Monthly restore drill on a throwaway compose project.

### 8.2 Laptop/dev
`docker compose -f deploy/compose.yml -f deploy/compose.local.yml up` with a local `./data/media` dir instead of the NAS. Use it for development and trying things out.

### 8.3 Cloud (if someone wants it hosted)
**Preferred: one small VM running the same compose file** (`compose.cloud.yml`). Use Hetzner, Lightsail or EC2 with 4 vCPU and 8–16 GB RAM.
- **No local LLM** (GPU VMs are expensive). Route all AI tasks to Bedrock, Anthropic or OpenAI, keeping `restricted_tags` handling in mind (those documents get no AI, or a small CPU model).
- **Storage**: Paperless media on an attached block volume, and restic nightly to S3/B2. **The WD stays the permanent home copy**: the home host (or any always-on LAN device) runs a scheduled `rclone`/`restic` pull over Tailscale from the VM onto the NAS. This keeps STO-01.
- **Access**: Tailscale-only (best), or Caddy with TLS plus Paperless/DocuHive auth plus fail2ban if public access is required.

**Scale-out option (multi-user, not for personal use)**: AWS ECS Fargate, RDS Postgres (pgvector), EFS for media, ElastiCache Valkey, Bedrock, ALB with Cognito. It costs more and has more moving parts; consider it only if this becomes a hosted product.

## 9. Phases

Each phase ends in something usable. Estimates assume part-time evenings.

### Phase 0 — Foundations (week 1)
- Repo skeleton (§3), licence, `AGENTS.md`, `.env.example`, `.gitignore`, gitleaks, and GitHub Actions running ruff, pytest, eslint, tsc and the synthetic evals.
- Overlay loader plus a test proving the overlay overrides the defaults.
- Spike: confirm against the running 3.1.x instance the Paperless webhook payload, `post_document` custom-field params, and the API version header.
- **Exit**: CI is green, `docuhive --help` runs, and the overlay mechanism is tested.

### Phase 1 — Core archive on the NAS (week 2)
- Compose: Paperless 3.1.x, Postgres 16 + pgvector, Valkey, nas-check, optional Gotenberg/Tika.
- NAS share, mount and sentinel. Storage path templates. Trash delay. Tailscale.
- `backup.sh`, a restic target and the restore runbook.
- Connect the iOS Paperless app.
- **Exit**: a doc uploaded from phone and web lands on the NAS, OCR'd and searchable. Killing the NAS mount stops Paperless. A restore drill succeeds.

### Phase 2 — AI layer + auto-classification (weeks 3–4)
- Paperless client, DB models + Alembic, job queue, worker loop.
- Provider router (Ollama, Anthropic, OpenAI, Bedrock, LiteLLM), agent harness, `ai_runs`.
- Default `taxonomy.yaml` plus your overlay taxonomy. Classify + extract agents. Webhook + poll fallback. Review tagging.
- Eval harness, plus a golden set of about 100 of your docs.
- **Exit**: new docs are auto-classified within 5 min. The eval report compares at least two models. The chosen model meets ≥ 90% on category and type before auto-apply is turned on.

### Phase 3 — Email ingestion (weeks 5–6)
- OAuth flows (Google Cloud project, Azure app registration for personal accounts), with encrypted token storage.
- Gmail, Graph and IMAP connectors. Pre-filter. AI triage. Import with provenance. Ledger and dedupe.
- Incremental sync scheduler. Backfill jobs with progress and resume.
- **Exit**: a one-year backfill on Gmail and Outlook completes. Re-running it imports 0 new items. Triage decisions are listed with reasons. Killing the worker mid-backfill and restarting it resumes cleanly.

### Phase 4 — Web UI (weeks 7–8)
- Auth: a login form exchanges credentials at Paperless `/api/token/`. The token sits in an httpOnly session cookie, server side only.
- Dashboard, review queue (accept, fix or reject AI suggestions in one click), search (full-text + filters), document detail with a preview proxied from Paperless, sources/backfill management, and a settings view showing routing and privacy (read-only first; editing later).
- **Exit**: daily use without opening the Paperless UI. Clearing the review queue takes under 10 s per doc.

### Phase 5 — Semantic search + Ask (weeks 9–10)
- Chunking, embeddings, pgvector HNSW, backfilling embeddings for existing docs.
- `doc_facts` mirror. Ask agent with tools (§5.4). SSE chat UI with citations. Saved analyses.
- Q&A eval set (~30 questions with expected cited docs and numbers).
- **Exit**: "How much did I spend on electricity in 2025?" returns a total computed by `query_facts`, with every source invoice cited. The Q&A eval passes its target.

### Phase 6 — Mobile capture + hardening (weeks 11–12)
- PWA manifest, the `/capture` page, multi-photo-to-PDF, served over Tailscale HTTPS.
- Notifications plugin (ntfy). Reminders for due and renewal dates from `doc_facts`.
- `compose.cloud.yml`, plus the cloud-to-NAS sync script and docs.
- Security pass: dependency audit, secret scan, permission tests (user A cannot retrieve user B's docs via chat or semantic search).
- **Exit**: photo-to-classified-doc works from a phone away from home. The cloud profile deploys from the docs alone. The security checklist is done.

### Later / backlog
- Vision-OCR for poor scans (LLM with vision as a second pass).
- Taxonomy editor in the UI.
- Multi-user household roles.
- Telegram/WhatsApp forward-to-archive.
- Migration off the WD after its December 2026 end of support. Nothing changes but the mount path.

## 10. Testing strategy

- **Unit**: prefilter rules, taxonomy validation, overlay merge, router selection, privacy gate, fact aggregation, dedupe (pytest). Web: component tests only where there is logic.
- **Integration**: docker-compose test stack with a real Paperless, recorded Gmail/Graph fixtures (no live accounts in CI), and a fake LLM provider returning canned structured output.
- **Evals**: the synthetic set runs in CI; the golden set runs locally before changing a model or prompt.
- **Ops**: restore drill, NAS-down drill, and provider-down drill (falls back or queues; no data loss).

## 11. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| WD EX2 Ultra end of support (Dec 2026) | LAN-only, no WD cloud. Storage is just a mount, so swap NAS/disk later. Independent restic copy. |
| NAS unavailable → silent local writes | nas-check sentinel + compose dependency + alerting. |
| Gmail testing-mode tokens expire after 7 days | Publish the personal GCP app to production (unverified) or use IMAP with an app password. |
| Wrong amounts/dates from LLM | Typed validation, confidence threshold, review queue, numbers only via `query_facts`. |
| Sensitive docs sent to cloud AI | Privacy gate before every call, local-only switch, restricted tags, audit in `ai_runs`. |
| Paperless API changes on upgrade | Pinned tag, explicit API version header, integration tests against the pinned image before upgrading. |
| Cost spike on backfill with cloud AI | Default local for triage/classify, monthly budgets, backfill auto-pause. |
| Copilot backend breaks | Marked experimental, with automatic fallback route. |

## 12. What you need (shopping/setup list)

1. **Always-on host**: an existing PC or Mac, or a mini PC (16 GB minimum, 32 GB recommended, NVMe). Docker, Tailscale.
2. **WD EX2 Ultra**: updated to the latest OS 5, healthy drives, RAID 1, a `paperless` share over NFS/SMB, cloud features off.
3. **Second backup target**: a USB disk and/or a B2/S3 bucket.
4. **Accounts**:
   - Google Cloud project (Gmail API OAuth client)
   - Azure app registration (personal Microsoft accounts, `Mail.Read`, `offline_access`)
   - Optional API keys: Anthropic, OpenAI, AWS (Bedrock)
   - Tailscale (free personal)
5. **Phone**: Swift Paperless (iOS) or the DocuHive PWA (iOS and Android).
6. **Private GitHub repo** `docuhive-local` for the overlay.

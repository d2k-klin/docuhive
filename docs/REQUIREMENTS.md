# DocuHive — Requirements

Status: draft v0.1 · 2026-11-03

## 1. Vision

A self-hosted, open-source personal document hub. Every important document, whether it arrives
by email, gets photographed on a phone, or comes off a scanner, ends up in one permanent archive on
my own storage (WD My Cloud EX2 Ultra). It is OCR'd, categorised by content, and easy to find.
I can ask questions across it ("what did I pay for electricity in 2025?", "when does my car
insurance renew?") using whichever AI provider I choose, including a fully local one.

## 2. Key decisions (from the analysis)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Paperless-ngx 3.1.x is the system of record** (storage, OCR, full-text search, users, permissions, mobile app compatibility). DocuHive does **not** reimplement any of this. | It is mature, OSS (GPL-3.0), and already does 70% of the job. We integrate through its REST API only. |
| D2 | **DocuHive is a companion app**: email ingestion with AI triage, a multi-provider AI layer (classification, extraction, Q&A), and its own web UI. | Paperless mail rules are rule-based only, and its native AI supports only Ollama/OpenAI-compatible backends. The multi-provider and email-backfill requirements need our own layer. |
| D3 | **One metadata writer.** DocuHive's classifier writes metadata. Paperless's "Apply AI Suggestions" workflow stays disabled. | Two AI services editing the same fields produce inconsistent results. |
| D4 | **Strands Agents SDK (Python)** is the agent framework. | Native providers: Bedrock, Anthropic, OpenAI, Ollama, plus LiteLLM, which covers GitHub Copilot and others. |
| D5 | **Languages: Python** (API, workers, agents) and **TypeScript/Next.js** (web UI). | User constraint. |
| D6 | **Public OSS core + private overlay.** The public repo holds generic code. Personal taxonomy, prompts, rules, plugins and eval data live in a separate private repo mounted at runtime. | Lets the project be OSS without leaking personal configuration. |
| D7 | **The WD NAS is file storage only.** Compute, the database and indexes run on an always-on host. | The EX2 Ultra (ARM dual-core, 1 GB RAM) cannot run Paperless, a database or an LLM. |

Assumption: "harness" means (a) a provider-agnostic **agent harness** that runs agents with tools,
budgets and audit logs, and (b) an **eval harness** that scores classification and Q&A quality per
model. If it meant Harness.io CI/CD, see open question Q1.

## 3. Users & context

- **Primary user:** the owner (single household, 1–4 users). Technical, self-hosting.
- **Documents:** invoices, receipts, bank and insurance statements, contracts, payslips, tax,
  medical, ID copies, warranties, letters. Mixed languages, at minimum English and German.
  Other languages are configurable.
- **Volume target:** about 20k documents over the archive's lifetime, about 50–200 new per month,
  and a one-time email backfill of several years.

## 4. Functional requirements

### 4.1 Storage & permanence (STO)
- **STO-01** All original files and archival PDFs are stored on the WD NAS (Paperless `media` dir via NFS/SMB).
- **STO-02** Originals are never modified or deleted automatically. DocuHive has no delete capability. Paperless trash auto-empty is disabled or set very long.
- **STO-03** The NAS folder tree follows the category (`<category>/<year>/<title>.pdf`) via Paperless storage paths, so the archive stays browsable without the app. Humans only read the share; Paperless owns the files.
- **STO-04** Paperless must refuse to start if the NAS mount is missing, so it never writes silently to local disk.
- **STO-05** Nightly backup: a Paperless `document_exporter` export plus a DB dump to the NAS, and an independent copy (restic) to a second target (USB disk and/or S3-compatible). A restore drill is documented and tested.

### 4.2 Email ingestion (MAIL)
- **MAIL-01** Connect multiple accounts: **Gmail** (Gmail API, OAuth2), **Outlook/Live/Hotmail** (Microsoft Graph, OAuth2), and **generic IMAP** (OAuth2 or app password).
- **MAIL-02** **Incremental sync** on a schedule (default every 15 min) using provider cursors (Gmail `historyId`, Graph delta, IMAP `UIDNEXT`).
- **MAIL-03** **Backfill**: scan a chosen date range per account (e.g. 2019-01-01 → today), resumable and idempotent, with visible progress.
- **MAIL-04** **Pre-filter** (cheap, no AI): attachment types (pdf, images, office docs), sender allow/deny lists, size limits, folder/label scope, and ignoring newsletters and promos (Gmail categories, `List-Unsubscribe`).
- **MAIL-05** **AI triage**: for each candidate, decide *is this a document worth archiving?* (invoice yes, marketing flyer no). It returns a decision, a reason and a confidence.
- **MAIL-06** Import accepted attachments into Paperless with provenance metadata: source account, message-id, sender, subject and received date.
- **MAIL-07** Optional: archive the email body itself (e.g. HTML-only receipts) as a PDF.
- **MAIL-08** Never delete or move emails. Optionally add a label/category such as `DocuHive/Imported` (configurable, off by default).
- **MAIL-09** Deduplicate by provider message-id plus attachment SHA-256. Re-running a backfill imports nothing twice.
- **MAIL-10** Every triage decision is logged and reviewable, and a rejected item can be imported manually.

### 4.3 Mobile & other capture (CAP)
- **CAP-01** Photograph or scan documents on a phone and upload them. v1 supports existing Paperless mobile apps (e.g. Swift Paperless on iOS) through the Paperless API.
- **CAP-02** A DocuHive **PWA capture page** (iOS and Android, installable) takes one or more photos, optionally merges them into one PDF, and uploads.
- **CAP-03** Watched "consume" folder on the NAS for desktop scanners and drag-and-drop.
- **CAP-04** Uploads from the web UI (drag-and-drop, multi-file).
- **CAP-05** Remote capture works away from home through private networking (Tailscale/WireGuard), with no public exposure by default.

### 4.4 Classification & extraction (CLS)
- **CLS-01** Every new document (any source) is classified automatically after OCR: **category**, **document type**, **correspondent**, **tags**, **title** and **document date**.
- **CLS-02** **Controlled vocabulary**: categories, types and tags come from a taxonomy file (YAML). The AI picks from that list and may only *propose* new terms, which go to review.
- **CLS-03** Category maps to a Paperless storage path (folder on the NAS).
- **CLS-04** **Structured extraction** per document type into Paperless custom fields, defined in the taxonomy. Examples: invoice → amount, currency, due date, invoice no.; contract → start, end, notice period; insurance → policy no., renewal date, premium.
- **CLS-05** **Confidence threshold**: above it, apply automatically. Below it, apply what is certain and tag `needs-review`.
- **CLS-06** Re-classify on demand (single document or a bulk filter), e.g. after a taxonomy change.
- **CLS-07** Every AI decision stores the model, prompt version, raw output, confidence and cost for audit.

### 4.5 Search & discovery (SRCH)
- **SRCH-01** Full-text search (Paperless index) with filters: category, type, correspondent, tags, date range, source.
- **SRCH-02** **Semantic search** ("the letter about my pension change") using embeddings.
- **SRCH-03** Results show a preview, metadata and a link to open or download the original.
- **SRCH-04** "Similar documents" from any document.

### 4.6 Ask & analyse (QA)
- **QA-01** Chat over the whole archive or a filtered subset (e.g. "only insurance, 2024–2026").
- **QA-02** Every answer **cites source documents** with links. An answer without sources is labelled as such.
- **QA-03** Numeric questions (totals, averages, trends) are computed from **extracted structured fields** by a tool, not by LLM arithmetic. The answer shows the rows it used.
- **QA-04** Saved analyses/reports ("annual utilities spend", "contracts expiring in 90 days") that can be re-run.
- **QA-05** Proactive reminders (optional, later): upcoming due dates, renewals and contract notice deadlines.
- **QA-06** Agent tools respect the asking user's Paperless permissions.

### 4.7 AI providers (AI)
- **AI-01** Supported providers: **Ollama (local)**, **Anthropic Claude**, **OpenAI**, **AWS Bedrock**, **GitHub Copilot** (via LiteLLM, experimental), and any **OpenAI-compatible** endpoint.
- **AI-02** **Per-task routing**: separate provider and model for triage, classification, extraction, embeddings and chat (e.g. local for bulk work, Claude for chat).
- **AI-03** **Privacy mode**: a global "local-only" switch, plus per-tag rules (e.g. `private`, `medical`, `id-document` → local models only). Cloud providers never receive restricted documents.
- **AI-04** Budgets: monthly token/cost cap per provider, with backfill jobs pausing when the cap is reached.
- **AI-05** Provider and model are swappable through config with no code change.

### 4.8 Web interface (WEB)
- **WEB-01** Next.js web app: login, dashboard (ingest stats, recent docs, job status), review queue, search, document detail, ask/chat, sources (mail accounts, backfills), taxonomy view, settings (providers, routing, privacy).
- **WEB-02** Responsive and usable on mobile, with the capture page as an installable PWA.
- **WEB-03** The Paperless UI remains available for power-user administration.

### 4.9 Customisation & extensibility (EXT)
- **EXT-01** **Private overlay**: a path (`DOCUHIVE_OVERLAY_DIR`) to a private repo containing taxonomy, prompts, mail rules, provider routing, custom plugins, eval data and compose overrides. Never committed to the public repo.
- **EXT-02** Plugin hooks (Python entry points): custom triage rules, post-classification actions, extra extractors and agent tools.
- **EXT-03** Defaults in the public repo work out of the box; the overlay only overrides.

### 4.10 Automation (AUTO)
- **AUTO-01** The whole pipeline (email → triage → import → OCR → classify → extract → index) runs unattended.
- **AUTO-02** Jobs are retryable with backoff. Failures are visible in the UI and never lose the source file.
- **AUTO-03** Optional notifications for failures, review queue size and reminders (e.g. ntfy, email or Telegram, through a plugin).

## 5. Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR-01 Privacy | Default install sends nothing to the internet except mail-provider APIs. Cloud AI is opt-in. |
| NFR-02 Security | No public ports by default (Tailscale). Secrets in `.env`/secret files, never in git. OAuth refresh tokens encrypted at rest. The NAS share is not reachable from the internet, and WD cloud/remote access is disabled. |
| NFR-03 Durability | No single failure (disk, NAS, host) loses documents. 3-2-1 backup rule. |
| NFR-04 Performance | New document classified within 5 min on the recommended host. Search under 1 s. Chat first token under 5 s with cloud models. Local is model-dependent. |
| NFR-05 Hardware | Runs on a 16 GB RAM host (cloud AI) or 32 GB (local 7–8B models). NAS is storage only. |
| NFR-06 Portability | Docker Compose deployment on Linux (preferred), macOS or Windows (WSL2). Same images for cloud. |
| NFR-07 Upgradability | Paperless version pinned. The API version header is set explicitly. DB migrations are versioned (Alembic). |
| NFR-08 Observability | Structured logs. Job and AI-run tables visible in the UI. Health endpoint. |
| NFR-09 Quality | Classification accuracy is measured by the eval harness per model. Target ≥ 90% on category and type for the golden set before enabling auto-apply. |
| NFR-10 Licensing | DocuHive under a permissive OSS licence (proposed Apache-2.0). Paperless (GPL-3.0) runs as a separate service and is integrated over HTTP only. |

## 6. Constraints & known risks

- **WD My Cloud EX2 Ultra support ends December 2026** (My Cloud OS 5 is supported until at least the end of 2026). After that there are no security fixes. Mitigation: LAN-only, all WD cloud/remote features off, and treating the storage as a replaceable mount. Any NAS or USB disk works later.
- **Gmail OAuth**: `gmail.readonly` is a restricted scope. For personal use, run your own Google Cloud project. In "Testing" status, refresh tokens expire after 7 days, so the app must be moved to "In production" (unverified, personal) or use IMAP with an app password.
- **Outlook.com** no longer allows basic-auth IMAP, so OAuth2 via Microsoft Graph is required.
- **GitHub Copilot** as an API backend is unofficial for this use case and may break or conflict with its terms. It is marked experimental.
- LLM extraction errors on amounts and dates are handled by validation, confidence thresholds and the review queue (QA-03, CLS-05).

## 7. Out of scope (v1)

- A native mobile app (PWA plus existing Paperless apps cover capture).
- Multi-tenant SaaS hosting.
- Editing document content. E-signatures.
- Running AI on the NAS.

## 8. Open questions

- **Q1** By "harness", did you mean the agent/eval harness assumed above, or Harness.io CI/CD? (CI defaults to GitHub Actions.)
- **Q2** Which always-on host do you have? This decides local-model feasibility (see the plan, §8).
- **Q3** Is the NAS currently RAID 1, and what free capacity does it have?
- **Q4** Which languages do your documents use, beyond English and German?
- **Q5** Licence choice: Apache-2.0 (proposed) or AGPL-3.0, which forces hosted forks to share their changes?
- **Q6** How many years of email to backfill, and which accounts?

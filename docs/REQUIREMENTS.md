# DocuHive — Requirements

Status: draft v0.3 · 2026-11-03 · own-core design (replaces the Paperless-based v0.1, commit `2f38128`) · v0.3 adds learning, guidance and UX requirements

## 1. Vision

A self-hosted, open-source personal document hub. Every important document, whether it arrives
by email, gets photographed on a phone, or comes off a scanner, ends up in one permanent archive on
my own storage (WD My Cloud EX2 Ultra). It is OCR'd, categorised by content, and easy to find.
I can ask questions across it ("what did I pay for electricity in 2025?", "when does my car
insurance renew?") using whichever AI provider I choose, including a fully local one.

DocuHive is also a **learning project**: a developer who clones it should see, run and understand how
to build agents with the Strands Agents SDK, wrap them in an agent harness, evaluate them and build
hybrid search, both from the docs and from inside the running app.

## 2. Key decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **DocuHive owns the whole document core.** No Paperless-ngx or other DMS as a backend. | One database, one permission model, one UI. No sync glue. An AI-first design without working around another app's data model. |
| D2 | **Build on proven libraries, not from scratch**: OCRmyPDF + Tesseract (OCR, PDF/A), Gotenberg (office files and email → PDF), Postgres full-text search + `pg_trgm` + `pgvector`, and the browser's native PDF viewer (pdf.js later if needed). | OCR and format conversion are where DMS projects spend years. These libraries already solve them. |
| D3 | **The vault on the NAS is the source of truth.** Each document is a folder holding the unchanged original, an OCR'd PDF/A copy and a `meta.json`. The database is an index that can be rebuilt from the vault. | The archive must outlive the app. Even with the DB lost or the app abandoned, the files and their metadata stay readable. |
| D4 | **Originals are never moved or renamed after import.** A browsable folder tree by category is an optional view the app generates, which it can throw away and rebuild. | Moving files on metadata changes is a common source of DMS bugs and lost files. |
| D5 | **Strands Agents SDK (Python)** is the agent framework. | Native providers: Bedrock, Anthropic, OpenAI, Ollama, plus LiteLLM, which covers GitHub Copilot and others. |
| D6 | **Languages: Python** (API, worker, agents, ingest) and **TypeScript/Next.js** (web UI). | User constraint. |
| D7 | **Public OSS core + private overlay.** Personal taxonomy, prompts, rules, plugins and eval data live in a separate private repo mounted at runtime. | Lets the project be OSS without leaking personal configuration. |
| D8 | **The WD NAS stores files only.** Compute, the database and indexes run on an always-on host. | The EX2 Ultra (ARM dual-core, 1 GB RAM) cannot run OCR, a database or an LLM. |
| D9 | **Learning is a product feature.** Every agent, harness, eval or search concept ships with a learning note, a runnable example and an in-app trace. | The project exists to teach Strands and agent harnesses (§5.14). |
| D10 | **Conventions are written as project skills** (`.agents/skills/`, with pointers in `.claude/skills/`), following the sibling d2k-klin repos. | Two developers and their coding agents produce one consistent product. |

Assumption: "harness" means (a) a provider-agnostic **agent harness** that runs agents with tools,
budgets and audit logs, and (b) an **eval harness** that scores classification and Q&A quality per
model. If it meant Harness.io CI/CD, see open question Q1.

## 3. Lessons from existing projects

Paperless-ngx, Docspell, Papra, Paperwise and Mayan EDMS were reviewed. These are the requirements they taught us:

| Pitfall seen | Our requirement |
|--------------|-----------------|
| Files renamed or moved on metadata change; users moving files on the share | STO-02, STO-03: immutable originals, generated read-only library view |
| App-specific storage that is unusable without the app | STO-04: self-describing vault with `meta.json`, rebuildable DB |
| Network mount missing → writes go to local disk silently | STO-05: vault health check, local staging buffer |
| Watching folders on NFS/SMB with inotify does not work | CAP-03: polling consume folder |
| Uploads lost on OCR failure | ING-04: quarantine, never delete input until stored |
| Tag sprawl from AI ("Electric", "Power Bill", …) | CLS-02: controlled vocabulary |
| Wrong amounts and dates from LLMs | CLS-05, QA-03: typed validation, review queue, no LLM arithmetic |
| Semantic search leaking documents across users | AUTH-03: permissions enforced inside every SQL query |
| Scope creep into enterprise features (versions, workflows, ACL matrices) | §7 out of scope |
| AGPL dependencies ending up linked into the app | NFR-10: licence-checked dependencies, AGPL tools only as subprocesses |

## 4. Users & context

- **Primary user:** the owner (single household, 1–4 users). Technical, self-hosting.
- **Documents:** invoices, receipts, bank and insurance statements, contracts, payslips, tax,
  medical, ID copies, warranties, letters. Mixed languages, at minimum English and German.
  Other languages are configurable.
- **Volume target:** about 20k documents over the archive's lifetime, about 50–200 new per month,
  and a one-time email backfill of several years.

## 5. Functional requirements

### 5.1 Storage & permanence (STO)
- **STO-01** All documents are stored in the **vault** on the WD NAS (NFS preferred, SMB supported).
- **STO-02** Each document lives in `vault/<YYYY>/<doc_id>/` and contains:
  - `original.<ext>`: byte-for-byte as received
  - `archive.pdf`: OCR'd, searchable PDF/A
  - `meta.json`: versioned schema with all metadata and provenance
  - `thumb.webp`

  The original is never modified, moved or renamed.
- **STO-03** Optional **library view**: `library/<category>/<year>/<date> <title>.pdf`, regenerated by the app (hardlinks on NFS, or skipped). The app can delete and rebuild it, and humans only read it.
- **STO-04** **Rebuildable index**: `docuhive vault rebuild` reconstructs the DB (documents, tags, facts, full-text index) from `meta.json` files alone. Embeddings are re-computed.
- **STO-05** If the NAS is unavailable, ingestion keeps accepting files into a **local staging area** on the host SSD and writes them to the vault once it is back. Nothing is written into an unmounted mount-point directory.
- **STO-06** Deletion is soft only (trash) in the UI. Permanent purge is an admin CLI action with confirmation. Nothing is deleted automatically.
- **STO-07** All vault writes are atomic: write a temp file, fsync, verify the checksum, then rename.
- **STO-08** Nightly backup: a DB dump into `vault/_system/`, plus an independent restic copy of the whole vault to a second target (USB disk and/or S3-compatible). A restore drill is documented and tested.

### 5.2 Ingestion pipeline (ING)
- **ING-01** One pipeline for all sources: receive → stage → dedupe → convert → OCR → extract text → thumbnail → write vault → index → classify.
- **ING-02** Formats:
  - PDF (born-digital and scanned)
  - images: JPEG, PNG, HEIC, TIFF
  - office documents: docx, xlsx, odt
  - email: `.eml`, and HTML bodies
- **ING-03** OCR in configured languages (default `deu+eng`), with automatic rotation and deskew. Pages that already contain text are not OCR'd again.
- **ING-04** Failures (corrupt file, encrypted PDF, unsupported type) go to a **quarantine** list with the reason. The input is kept and can be retried. An input is never deleted until its vault write is verified.
- **ING-05** **Duplicate detection** by SHA-256 of the original, per owner. A duplicate is reported, not imported again.
- **ING-06** Password-protected PDFs: try an empty password, otherwise quarantine with reason `encrypted`. Supplying a password in the UI comes later.
- **ING-07** Processing status is visible per document (queued, OCR, classifying, done, failed).

### 5.3 Email ingestion (MAIL)
- **MAIL-01** Connect multiple accounts: **Gmail** (Gmail API, OAuth2), **Outlook/Live/Hotmail** (Microsoft Graph, OAuth2), and **generic IMAP** (OAuth2 or app password).
- **MAIL-02** **Incremental sync** on a schedule (default every 15 min) using provider cursors (Gmail `historyId`, Graph delta, IMAP `UIDNEXT`).
- **MAIL-03** **Backfill**: scan a chosen date range per account (e.g. 2019-01-01 → today), resumable and idempotent, with visible progress.
- **MAIL-04** **Pre-filter** (cheap, no AI): attachment types, sender allow/deny lists, size limits, folder/label scope, and ignoring newsletters and promos (Gmail categories, `List-Unsubscribe`).
- **MAIL-05** **AI triage**: decides *is this a document worth archiving?* It returns a decision, a reason and a confidence.
- **MAIL-06** Accepted attachments go through the ingest pipeline with provenance: source account, message-id, sender, subject and received date.
- **MAIL-07** Optional: archive the email body itself (e.g. HTML-only receipts) as a PDF.
- **MAIL-08** Never delete or move emails. Optionally add a label/category such as `DocuHive/Imported` (configurable, off by default).
- **MAIL-09** Deduplicate by provider message-id plus attachment SHA-256. Re-running a backfill imports nothing twice.
- **MAIL-10** Every triage decision is logged and reviewable, and a rejected item can be imported manually.

### 5.4 Mobile & other capture (CAP)
- **CAP-01** **PWA capture** (iOS and Android, installable): take one or more photos, review and reorder pages, then upload as one document. It is the primary mobile path and ships early.
- **CAP-02** Images are compressed on the device before upload. Rotation and deskew happen on the server (ING-03).
- **CAP-03** A **consume folder** on the NAS for desktop scanners and drag-and-drop, watched by **polling**, because inotify does not work on network mounts.
- **CAP-04** Upload from the web UI (drag-and-drop, multiple files) and through the REST API with personal API tokens (for scripts and iOS Shortcuts).
- **CAP-05** Remote capture works away from home through private networking (Tailscale/WireGuard), with no public exposure by default.

### 5.5 Document management (DOC)
- **DOC-01** Document list with filters (category, type, correspondent, tags, date range, source, status), sorting and pagination.
- **DOC-02** Document detail: preview (native browser PDF viewer), metadata, extracted facts, provenance, AI decision history, notes, and download of the original or archive copy.
- **DOC-03** Edit metadata, with bulk edit on a selection. Every change updates `meta.json` and is recorded in an audit log.
- **DOC-04** Manage vocabulary: correspondents, tags, document types and categories, including merging duplicates.
- **DOC-05** Trash, with restore (STO-06).
- **DOC-06** Split and merge pages: backlog, not v1.
- **DOC-07** Every field shows who set it (AI with confidence, or the user). User-set fields are locked against AI and can be unlocked ("let AI manage again"). Every edit, including bulk edits, can be undone, and the change history is visible per document.
- **DOC-08** Users can set category and tags at upload time. These count as user-set fields.

### 5.6 Classification & extraction (CLS)
- **CLS-01** Every new document is classified automatically after OCR: **category**, **document type**, **correspondent**, **tags**, **title**, **document date** and **language**.
- **CLS-02** **Controlled vocabulary**: categories, types and tags come from a taxonomy file (YAML). The AI picks from that list and may only *propose* new terms, which go to review.
- **CLS-03** **Structured extraction** per document type into typed **facts**, defined in the taxonomy. Examples: invoice → amount, currency, due date, invoice no.; contract → start, end, notice period; insurance → policy no., renewal date, premium.
- **CLS-04** **Confidence threshold**: above it, apply automatically. Below it, apply what is certain and add the document to the **review queue**.
- **CLS-05** Typed validation of extracted values (date parsing, ISO currency, positive amounts, IBAN checksum). Invalid values go to review.
- **CLS-06** Re-classify on demand (single document or a bulk filter), e.g. after a taxonomy change. Manual edits are never overwritten by re-classification unless forced.
- **CLS-07** Every AI decision stores the model, prompt version, raw output, confidence and cost for audit.

### 5.7 Search & discovery (SRCH)
- **SRCH-01** Full-text search over title, content, correspondent and notes. It handles language-aware stemming (German and English), accents, and typos (trigram).
- **SRCH-02** **Semantic search** ("the letter about my pension change") using embeddings.
- **SRCH-03** **Hybrid ranking** combines full-text and semantic results in one query, with filters and permissions applied.
- **SRCH-04** Results show a thumbnail, a matched snippet with highlights, metadata and a link to open.
- **SRCH-05** "Similar documents" from any document.

### 5.8 Ask & analyse (QA)
- **QA-01** Chat over the whole archive or a filtered subset (e.g. "only insurance, 2024–2026").
- **QA-02** Every answer **cites source documents** with links. An answer without sources is labelled as such.
- **QA-03** Numeric questions (totals, averages, trends) are computed from **extracted facts** by a SQL tool, not by LLM arithmetic. The answer shows the rows it used.
- **QA-04** Saved analyses/reports ("annual utilities spend", "contracts expiring in 90 days") that can be re-run.
- **QA-05** Reminders (later): upcoming due dates, renewals and contract notice deadlines from facts.
- **QA-06** Agent tools only see documents the asking user may see (AUTH-03).
- **QA-07** **Intuitive chat:**
  - **Reachable everywhere:** a top-bar button, ⌘K, "Ask about this document" and "Ask about these documents".
  - **Suggested questions** built from the user's own archive.
  - **Visible, editable scope chips**, plus a local/cloud privacy badge.
  - **Answers:** streaming with Stop. Citations with previews. Fact tables with per-currency totals. "Open sources as list". Follow-up suggestions.
  - **Guidance when nothing is found or the question is ambiguous.**
  - **History**, and thumbs up/down feedback (which feeds evals).

### 5.9 Users & access (AUTH)
- **AUTH-01** Local user accounts with argon2-hashed passwords and secure session cookies. Passkeys/OIDC (e.g. Authentik) come later.
- **AUTH-02** Personal API tokens, scoped, revocable and listed in the UI.
- **AUTH-03** Each document has an owner and an optional "shared with household" flag. Every query, including full-text, vector search and agent tools, applies the same permission filter in SQL.
- **AUTH-04** An admin role for users, providers and system settings.

### 5.10 AI providers (AI)
- **AI-01** Supported providers: **Ollama (local)**, **Anthropic Claude**, **OpenAI**, **AWS Bedrock**, **GitHub Copilot** (via LiteLLM, experimental), and any **OpenAI-compatible** endpoint.
- **AI-02** **Per-task routing**: separate provider and model for triage, classification, extraction, embeddings and chat.
- **AI-03** **Privacy mode**: a global "local-only" switch, plus per-tag/per-category rules (e.g. `medical`, `id-document` → local models only). Cloud providers never receive restricted documents.
- **AI-04** Budgets: monthly cost cap per provider, with backfill jobs pausing when the cap is reached.
- **AI-05** Provider and model are swappable through config with no code change.

### 5.11 Web interface (WEB)
- **WEB-01** Next.js web app: login, dashboard (ingest stats, recent docs, job status, quarantine), documents, review queue, search, ask/chat, sources (mail accounts, backfills), vocabulary, settings (providers, routing, privacy, users, tokens).
- **WEB-02** Responsive and usable on mobile, with the capture page as an installable PWA.
- **WEB-03** Accessibility basics: keyboard navigation, labels, contrast.
- **WEB-04** **One design system** (`docuhive-ui` skill):
  - **Type:** one standard font (Inter, self-hosted), and a small type scale with page titles of at most 20px.
  - **Controls:** all of them (inputs, selects, comboboxes, date fields, buttons, tag inputs) share one height (36px), border, radius and focus ring. Checkboxes and radios are 16px, aligned with their labels.
  - **Layout:** a 4px spacing grid. Aligned page headers, forms, toolbars and tables.
  - **Themes and states:** light and dark themes. Loading, empty, error and processing states for every view.
  - **Check:** an automated control-height test on a kitchen-sink page.
- **WEB-05** A command palette (⌘K / Ctrl+K) for navigation, search and asking a question.

### 5.12 Customisation & extensibility (EXT)
- **EXT-01** **Private overlay**: a path (`DOCUHIVE_OVERLAY_DIR`) to a private repo containing taxonomy, prompts, mail rules, provider routing, plugins, eval data and compose overrides. Never committed to the public repo.
- **EXT-02** Plugin hooks (Python entry points): custom triage rules, post-classification actions, extra extractors and agent tools.
- **EXT-03** Defaults in the public repo work out of the box; the overlay only overrides.

### 5.13 Automation (AUTO)
- **AUTO-01** The whole pipeline (capture/email → ingest → classify → extract → index) runs unattended.
- **AUTO-02** Jobs are retryable with backoff. Failures are visible in the UI and never lose the source file.
- **AUTO-04** Once setup is complete, no routine user action is needed: mail sync, backfill, OCR, classification, extraction, indexing and reminders all run on their own. The user is asked only about low-confidence results, failures and expired consents. Manually uploaded documents get exactly the same analysis and storage as emailed ones.
- **AUTO-03** Optional notifications for failures, review queue size and reminders (e.g. ntfy, email or Telegram, through a plugin).

### 5.14 Learning (LRN)
- **LRN-01** A **learning path** in `docs/learn/`, ordered from simple to advanced. It covers:
  - Strands basics, structured output, model providers
  - the agent harness, privacy routing
  - tools and the agent loop, computing numbers without hallucination
  - embeddings and chunking, hybrid search
  - evals, the triage agent, job pipelines

  Each note links to the code, a runnable example and the screen where the concept is visible.
- **LRN-02** **Runnable examples** in `examples/learn/`, one concept each. They run with a fake model by default and with any real provider by flag, and are tested in CI.
- **LRN-03** **"How was this made?"**: every AI-produced value in the UI links to its run. The run page shows the route, local/cloud and why, the prompt name/version and text, input size, validated output, retries and fallbacks, a tool-call timeline, tokens, cost and latency, and a link to the learning note.
- **LRN-04** The README states what you'll learn. Settings → AI has a Learn tab, and the latest synthetic eval report is linked from it.

### 5.15 Guidance (GUIDE)
- **GUIDE-01** A **first-run setup wizard** walks through storage (NAS vault), AI provider choice and connection test, models per task (including `ollama pull` help), privacy, email accounts and backfill range, phone capture (a QR code + install steps) and notifications. It ends with "automation is running". Each step is resumable and can be skipped where safe.
- **GUIDE-02** A **dashboard setup checklist** built from `SetupCheck` items reported by each area. It reappears when something breaks (NAS offline, mail reauth needed, stale backup).
- **GUIDE-03** Every list or page has an **empty state** that explains it and offers one next action.
- **GUIDE-04** Every user-facing error says what happened, why, and what to do (a button or link). No raw codes or stack traces.
- **GUIDE-05** Settings and fields that need domain knowledge have a one-line description and an optional help popover linking to `docs/setup/` or `docs/learn/`. Jargon is explained on first use.
- **GUIDE-06** Long-running work (backfill, OCR, embedding, re-classification) shows progress, what is happening now, and what happens next. It can be paused or cancelled where safe.

### 5.16 Knowledge bases (KB)
Bedrock-style knowledge bases over the same index, for chat and for other agents. Decision: [0002](decisions/0002-knowledge-bases.md); plan: [shared/knowledge-bases.md](shared/knowledge-bases.md).
- **KB-01** A **knowledge base** is a named, saved scope (categories, types, senders, tags, dates, sources) with a description. It never copies documents. Users can own or share knowledge bases.
- **KB-02** **Hybrid chunk retrieval**: full-text (German/English stemming, accents, typos) and semantic results fused into one ranking, with permissions applied first.
- **KB-03** A **retrieve API** returns ranked chunks with scores, document links and metadata; an **ask API** returns an answer with citations. Both are scoped to one knowledge base and can only narrow it.
- **KB-04** An **MCP server** exposes list, retrieve, ask and read-document tools to other agents, with the same permissions.
- **KB-05** **Privacy across the API**: restricted documents are excluded from API and MCP results unless the token is explicitly marked as a local-only consumer. Responses report how many were excluded, never their content.
- **KB-06** Each knowledge base shows its **status**: documents in scope, indexed, pending, failed and stale, and the embedding model.
- **KB-07** A **test panel** shows what retrieval returns for a query (chunks, scores, mode) before an agent relies on it.
- **KB-08** **Retrieval quality is evaluated** (recall@k, MRR on a synthetic set; a private golden set in the overlay). Chunking, fusion and reranking change only with an eval result.

## 6. Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR-01 Privacy | Default install sends nothing to the internet except mail-provider APIs. Cloud AI is opt-in. |
| NFR-02 Security | No public ports by default (Tailscale). Secrets in `.env`/secret files, never in git. OAuth refresh tokens encrypted at rest. CSRF protection, upload size and type limits, and files rendered and converted in isolated containers. The NAS share is not internet-reachable, and WD cloud access is disabled. |
| NFR-03 Durability | No single failure (disk, NAS, host, DB) loses documents or their metadata. 3-2-1 backup rule. The vault alone is enough to recover. |
| NFR-04 Performance | A typical 1–5 page document is ingested (OCR) in under 60 s and classified in under 5 min on the recommended host. Search under 500 ms at 20k docs. Chat first token under 5 s with cloud models. |
| NFR-05 Hardware | Runs on a 16 GB RAM host (cloud AI) or 32 GB (local 7–8B models). NAS is storage only. |
| NFR-06 Portability | Docker Compose deployment on Linux (preferred), macOS or Windows (WSL2). Same images for cloud. |
| NFR-07 Upgradability | DB migrations versioned (Alembic). `meta.json` schema versioned with forward migrations. |
| NFR-08 Observability | Structured logs. Job, ingest and AI-run tables visible in the UI. Health endpoint. |
| NFR-09 Quality | OCR and classification measured by the eval harness. Target ≥ 90% on category and type for the golden set before enabling auto-apply. |
| NFR-10 Licensing | DocuHive under Apache-2.0 (proposed). Only permissive libraries are imported into our code (e.g. pypdfium2, not PyMuPDF). AGPL/GPL tools (Ghostscript, unpaper) are invoked only as separate processes. |

## 7. Out of scope (v1)

- A native mobile app (the PWA covers capture).
- Document versions, workflow engine, fine-grained ACLs, share links.
- Multi-tenant SaaS hosting.
- E-signatures, editing document content.
- Running AI or OCR on the NAS.

## 8. Constraints & known risks

- **WD My Cloud EX2 Ultra support ends December 2026** (My Cloud OS 5 is supported until at least the end of 2026). After that there are no security fixes. Mitigation: LAN-only, all WD cloud features off. The vault is a plain folder, so it moves to any NAS or disk later.
- **Building our own core** means taking on OCR and format edge cases. Mitigation: a Phase 0 spike on 50 real documents with a go/no-go gate. The Paperless-based plan (commit `2f38128`) stays as the fallback.
- **Gmail OAuth**: `gmail.readonly` is a restricted scope. For personal use, run your own Google Cloud project. In "Testing" status, refresh tokens expire after 7 days, so the app must be moved to "In production" (unverified, personal) or use IMAP with an app password.
- **Outlook.com** no longer allows basic-auth IMAP, so OAuth2 via Microsoft Graph is required.
- **GitHub Copilot** as an API backend is unofficial for this use case and may break or conflict with its terms. It is marked experimental.
- **iOS PWA camera**: no native document scanner (edge detection). The first version is photos plus server-side deskew. Client-side edge cropping is a later improvement.

## 9. Open questions

- **Q1** By "harness", did you mean the agent/eval harness assumed above, or Harness.io CI/CD? (CI defaults to GitHub Actions.)
- **Q2** Which always-on host do you have? This decides local-model feasibility and OCR speed.
- **Q3** Is the NAS currently RAID 1, and what free capacity does it have? Can it export NFS?
- **Q4** Which languages do your documents use, beyond English and German?
- **Q5** Licence choice: Apache-2.0 (proposed) or AGPL-3.0, which forces hosted forks to share their changes?
- **Q6** How many years of email to backfill, and which accounts?

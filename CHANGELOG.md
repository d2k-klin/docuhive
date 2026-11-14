# Changelog

Changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and SemVer.

## [Unreleased]

## [0.6.0] - 2026-11-14

### Security

- Files DocuHive creates in the vault and staging folders are closed to other accounts on the host or NAS (`DOCUHIVE_UMASK`, default `027`). Files stored earlier keep their permissions; close them once with `chmod -R o-rwx` on the vault folder. Set `DOCUHIVE_UMASK=022` only if another account must read the vault directly.
- A session is renewed while in use but ends 90 days after sign-in at the latest.
- The operations guide says how to protect the storage: disk or volume encryption, file permissions, encrypted backups.

### Fixed

- **Sources**, **AI settings** and loading placeholders pass the accessibility and control-size checks: the mailbox provider choices, the document link in AI activity (it was distinguishable by colour only) and the loading state's label.
- Database tests selected by name fail without a database instead of being skipped.

### Changed

- The five first user journeys (setup checklist, upload and review, upload locks, three-page capture, offline capture queue) run against the real stack at phone, tablet and desktop width in light and dark, instead of being switched off. The test stack reads uploads with real OCR and restarts killed services like production.
- `ai`, `mail` and `notify` read the public address and shipped defaults through the public configuration contract (`config.public_url()`, `config.default_yaml()`).
- Project status: production-ready, declared by the owner ([decision 0005](docs/decisions/0005-production-status.md)). The README, installation guide and production-readiness plan say what is verified and what is not.

## [0.5.0] - 2026-11-12

### Added

- Shared document categories: select predefined categories and add custom ones in Vocabulary. Choices apply to uploads, edits and AI classification; disabling a category preserves existing documents and privacy rules.
- Live AI progress on uploads, document lists and document details, including queued work, analysis, review, completion, retries and failures.
- Last month and last quarter document filters, with a shortcut to save the current group in the sidebar. Date filtering uses the printed date, falling back to the upload date when missing.
- **Change storage** on Storage health: admins choose the vault folder on a mounted share or disk, or create one. The folder must be inside the storage root that Compose mounts at install (`DOCUHIVE_STORAGE_ROOT_HOST_DIR`, default `/srv/docuhive/storage`, created if missing). Only safe switches are allowed: a new vault in an empty folder while the archive is empty, or the archive's own vault at a new place. Other files, another archive's vault, symlinks and paths outside the root are refused, and nothing is moved or deleted.

### Changed

- **Sources** guides you through choosing a provider, connecting securely, and importing existing attachments. Google and Microsoft sign-in are the primary paths when configured; app-password guidance and one-time server setup instructions are shown in the page. Custom mailboxes have explicit server, username and folder settings. Successful connections offer a history range immediately, with live import progress and email activity.
- Mailbox login failures are explained in plain words: server not found, no answer on that port, or login refused, with the app-password hint.
- The scanner folder defaults to the chosen vault's `consume` folder; Compose no longer pins it to `/srv/vault/consume`.
- Dependencies: pydantic 2.14.3, FastAPI 0.162, SQLAlchemy 2.1.8, Strands Agents 1.64, import-linter 2.16, Playwright 1.65, lucide-react 1.70.

### Fixed

- Gmail, iCloud and Yahoo app passwords pasted with their display spaces (`abcd efgh ijkl mnop`) now log in; a refused login shows the mail server's own reply.

### Security

- A refused mailbox login never shows the password, even when the mail server repeats it in its reply.

## [0.4.1] - 2026-11-05

### Added

- **Storage health** now says which storage the archive uses: its location (the host path, through the new display-only `DOCUHIVE_VAULT_LABEL` and `DOCUHIVE_STAGING_LABEL`), network share or local disk, vault ID, document count and free space. It also shows uploads waiting in local staging (`GET /api/system/storage`, admins only).
- The installation guide covers a vault on a local disk when there is no NAS.

### Fixed

- IMAP connections queue their first sync immediately. Mail-server connections time out after 20 seconds; failed logins save no account and unexpected errors show actionable copy.
- Connecting Gmail or Outlook before its sign-in app was set up showed raw JSON. It now returns to **Sources** with a plain reason and a pointer to the setup guide, and suggests IMAP with an app password for Gmail. The OAuth callback's error message is now URL-encoded.

## [0.4.0] - 2026-11-05

### Changed

- Local AI defaults, measured on the synthetic set ([decision 0004](docs/decisions/0004-model-selection.md)):
  - classification moves to `ollama/gemma4:12b` (92.5% category against 47.5%), falling back to `qwen3:8b`;
  - extraction stays on `qwen3:8b` (95.3% of facts exact against 57.0%).
  Pull `gemma4:12b` to use it.
- Ollama's thinking is off by default (`providers.ollama.think`). It made answers no more accurate and 2–13 times slower, and it pushed calls into the timeout.

### Fixed

- Ask found nothing in a new archive. Until someone accepts the AI's suggestions, a document has no category, type or date, so the filters the model adds to its searches hid every unreviewed document. When the model's own filters match nothing, it now searches again within the user's chosen scope, which still applies, and says so.

## [0.3.2] - 2026-11-05

### Fixed

- A worker restarted after a crash now frees the jobs its predecessor was running at once, instead of leaving a scan in processing until its 30-minute lease expires. Live sibling processes on the same host are left alone.
- `backup.sh` refuses a missing vault marker with a clear message instead of a traceback.
- The Trash page no longer says an administrator can remove documents for good.

### Security

- The calendar feed takes its token in the URL, which calendar services store and may log. It accepted `read`, `write` and `admin` tokens, so a leaked feed address gave access to every document. It now accepts only a new `calendar` scope, which opens nothing else. Existing calendar subscriptions need a new token.
- The web app sends `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy: same-origin`.

## [0.3.1] - 2026-11-05

### Added

- An installation guide (`docs/setup/installation.md`), from an empty host to the first sign-in, and a user guide (`docs/user-guide.md`) for everyday use.

### Fixed

- Production containers had no supported way to receive AI keys, mail OAuth apps or notification settings: every backend container now reads a private `/etc/docuhive/app.env` (or `DOCUHIVE_APP_ENV`); it is optional, and the stack's own settings always win. Needs Compose 2.24 or newer.
- The README status, and the operations, NAS and capture guides, still described document intake and `vault init` as unavailable.

## [0.3.0] - 2026-11-04

### Added

- Security checklist (`docs/security-checklist.md`) with evidence for every item; a hostile-file corpus and a route permission matrix in the integration tests; `make perf-ingest` for upload-to-stored timing.
- Document screens: documents list with filters and bulk edit, document detail (PDF preview, editing with "set by you"/AI badges and unlock, facts, history, downloads, trash), search with highlighted snippets (`GET /api/search`), drag-and-drop upload that follows each file until it is stored, quarantine with plain-language reasons and retry, trash, vocabulary, account settings and the dashboard setup checklist.
- Document intake: `ingest.submit` (type and size checks, per-owner dedupe, staging) and the `ingest.process` job (conversion, OCR to PDF/A, thumbnail, verified vault write, quarantine with the input kept, retry). A NAS outage leaves uploads staged until the vault is back.
- The vault: `docuhive vault init`, an availability check against the vault id, atomic writes verified by checksum, and `meta.json` for every document, rendered from the database after each change.
- The documents service behind the contracts: reading, metadata changes with user locks, AI provenance, audit history, weighted search vectors and `document.*` events.
- Document API: list with filters, detail, original/archive/thumbnail files, history, edit, bulk edit, trash and restore, and quarantine retry. Uploads can set category and tags, which count as the user's choice.
- Tests for the scanner folder and the library view against the real document core.
- `docuhive ingest <files> --owner <user>`.
- `docuhive vault rebuild [--dry-run]`: recreates the database from the vault's `meta.json` files and archive copies, reporting unreadable folders instead of stopping. Missing owners are created disabled.
- `meta.json` schema versioning, `docuhive vault migrate`, and `meta.schema.json` in the vault.
- Vocabulary API (`/api/vocabulary/tags`, `/api/vocabulary/correspondents`): typeahead lists, and rename and merge for administrators; merged names keep resolving to the survivor.
- Phone capture with oriented/downscaled images, page ordering and an account-bound offline upload queue; scoped-token upload and durable scanner polling.
- Production containers, NAS/HTTPS guides, quiesced restic backups with a timer, backup warnings, managed library hardlinks and recovery/upgrade runbooks. Target-hardware acceptance remains pending.

### Changed

- OCR gate waived by the owner; the native core is selected and real-document measurements move to the release gate.
- A step that fails with a program error (not a document problem) is retried before the document is quarantined.

### Fixed

- The "How was this made?" page (`/settings/ai/runs/{id}`) exists now: model, prompt, privacy, tokens, cost, output and retries for one AI run. Links from Ask, Review, AI settings and document badges led to a missing page before.
- Clearing a field on the document page now empties it (`clear_fields` in `MetadataPatch`) instead of silently keeping the old value.
- Shared readers no longer see edit, trash or unlock controls on other members' documents; history and lock badges no longer attribute other people's changes to you.
- Quarantine reasons are plain language everywhere (upload, detail, quarantine), including OCR and conversion failures.
- Changing your password now explains that every session and API token ends and takes you to sign-in; the confirmation must match.
- Search no longer fails when the embedding model is unreachable; it falls back to word search.
- The document preview may frame the archive PDF from DocuHive's own origin; every other page still refuses framing.
- The capture page's service worker, queue script and manifest load without a session; before, the sign-in redirect stopped the service worker from installing.
- Lint, type and formatting errors from the capture change, which had turned `main`'s CI red.

### Security

- Log lines no longer carry passwords, tokens, session cookies or `Authorization` values (quoted, `Basic`, `Bearer` or in query strings); every handler masks them, uvicorn's and `--reload` children included, and access lines keep their format.
- A generated hostile-file corpus (zip bomb, scripted and looping PDFs, polyglot, oversized image, beacon email, scripted HTML) runs through the real pipeline; archives are checked inert on their decoded objects.
- A permission matrix walks every API route: no route answers without a session except sign-in, health and the token-authenticated calendar feed, and no document route serves a private document to another user, administrators included.

## [0.2.0] - 2026-11-04

### Changed

- The theme switch in the header is a sun/moon icon button instead of a text button.
- TypeScript 7 for the web app's typecheck and build, ocrmypdf 17, uvicorn 0.54 and psycopg 3.3.
- The worker image moves to Debian trixie (Ghostscript 10.05).

### Added

- Storage health: a weekly, read-only vault check (`docuhive vault check [--full]`, `/settings/storage`) that finds missing files, unreadable descriptions, changed originals and orphan folders without touching anything.
- Custom fields (`/settings/fields`): administrators define typed fields, optionally per document type and with date reminders; extraction, review, reminders and Ask use them like the built-in facts, while evals keep measuring the built-in taxonomy.
- Saved views (`/views`): named, shareable filters pinned to the sidebar, each with a paged document list.
- Near-duplicate detection (`/duplicates`): after indexing, documents are compared on sender, amount, date and meaning; pairs are only suggested, and a dismissed pair never returns. Learning note 13 and a runnable example explain the rules.
- Filtered export: a ZIP of archive PDFs plus a CSV of details for a saved view, knowledge base or filter, capped at 1000 documents, with spreadsheet formula injection neutralised, missing files listed and every export audited.
- `docs/FEATURES.md`: every feature in one sentence with its current state, linked from the README.
- Saved knowledge bases with owner-only editing, shared scopes, taxonomy validation, indexing status, suggestions and the `/knowledge` manager.
- API token settings with knowledge-base permissions and an explicit local-consumer trust flag; bearer tokens cannot grant that flag to new tokens.
- Hybrid retrieval learning note and offline example; chunk typo fallback and candidate diversification before fusion.
- System architecture illustrations covering the web/API, workers, OCR, agents, embeddings, PostgreSQL, file storage and knowledge bases, with incomplete components marked.
- `docs/ARCHITECTURE.md`: how DocuHive works, from the basics down to components, libraries, user actions, data flows, hosting, security and current status.
- Hybrid search: full-text (German/English stemming, accents, typo fallback) fused with semantic search by reciprocal rank fusion, with permissions and filters on both sides, and chunk-level `search.retrieve` for knowledge bases (KB-M1).
- Decision 0002 and an implementation plan for Bedrock-style knowledge bases inside DocuHive (retrieve and ask APIs, MCP server, retrieval evals), with requirements KB-01…KB-08.
- `make ocr-smoke` and a workflow that run real OCR inside the worker image, because unit tests mock ocrmypdf.

### Fixed

- The web app uses Inter again instead of the browser's default serif: the font variable was on `<body>`, but the font stack is resolved on `<html>`.
- The Ask page no longer crashes when a chat updates (an effect returned the Promise from `scrollIntoView`), and its suggestions no longer overflow on tablets.
- OCR in the container: ocrmypdf refused the bookworm image's Ghostscript 10.0.0 whenever existing text was skipped, so every scan failed.

## [0.1.0] - 2026-11-04

### Added

- Binding contract models, Python and web workspaces, CLI and health API.
- Validated core settings, private overlay merging, prompt versions and plugin hooks.
- Independent database migration environments and the core PostgreSQL schema.
- Durable jobs, retries, lease recovery, scheduler leadership and reusable platform fakes.
- Session and token authentication with CSRF checks and centralized document permissions.
- Isolated OCR spike, safe content detection, conversion, text extraction, previews and CER measurement.
- Streaming API proxy and generated TypeScript API types.
- Developer commands, disposable test stack, CI and contributor documentation.
- Mr.D brand assets with a manifest check, and a README in every folder describing each file.
- Real light and dark screenshots of the app, captured from the synthetic QA environment.

### Changed

- GitHub Actions (checkout, setup-node, setup-python, upload-artifact) move to v7; ESLint 10, lucide-react 1.x, openapi-fetch 0.17 and current Python dev tools.
- Dependabot updates Python through `uv`, so `uv.lock` stays in sync; Tailwind and `@types/node` majors are done by hand.
- The README follows the Hive project template: Mr.D hero, what DocuHive does, what you'll learn, quick start, documentation, honest project status.
- The documentation index is organised by Using, Understanding, Learning, Extending and Planning, and the link check covers every README.

### Security

- Select a patched Next.js release and current test tooling for the new web workspace.
- Record the unmeasured OCR gate explicitly; the archive backend remains unselected.

[Unreleased]: https://github.com/d2k-klin/docuhive/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/d2k-klin/docuhive/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/d2k-klin/docuhive/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/d2k-klin/docuhive/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/d2k-klin/docuhive/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/d2k-klin/docuhive/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/d2k-klin/docuhive/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/d2k-klin/docuhive/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/d2k-klin/docuhive/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/d2k-klin/docuhive/releases/tag/v0.1.0

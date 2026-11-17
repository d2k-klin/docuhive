# Changelog

Changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and SemVer.

## [Unreleased]

### Added

- Before a plugin sends anything by mail or makes a link, its page shows exactly what will go out (recipient, subject, text, attachments) with **Send now** and **Cancel**.
- Plugin pages show only the parts that apply: an issued invoice no longer offers "Issue" or "Delete draft".
- Landlords: rent and advance changes from a date, used by the rent ledger and the statement; a reminder letter for outstanding rent.
- Contracts: with the bank plugin, regular payments that have no contract are listed, to add as a contract or dismiss.
- Tax: the yearly VAT return with the advance returns already paid and what is left; each period lists the bookings behind its figures. Business equipment from the inventory and rental income from the landlord plugin appear in the tax plugin when those are on.
- **Settings → Users** for administrators: add people, change their role, disable or enable them, and choose which categories bookkeepers may see.
- A document's "Related" list shows the related documents' titles.
- Vocabulary marks categories and document types that a plugin added ("From steuer-de") instead of calling them custom.
- Tax invoices: **Correct this invoice** issues the cancelling credit note and opens a corrected copy in one step; saved items to add to a draft; a reminder when a recurring invoice has made a new draft.
- Tax books can be shared by user name with a bookkeeper (keeps the books; only the owner issues invoices) or someone who only looks. Plugins can look up people by user name with the new `users:find` capability; nothing else about a person is shared.
- **Settings → AI** lists each running plugin's AI tasks with the route they use (their own from `routing.yaml`, or the core task's route they borrow).
- Plugin forms: a document field is a search box over your documents instead of a list of the latest 200 (inventory "Add a document", the tax plugin's filing confirmation).
- Inventory: places inside places ("House › Kitchen"); Ask's place filter includes what is inside.
- Inventory: **Merge with another item** for the same thing listed twice; its documents and missing details move over.
- **Use in Ask** per plugin on Settings → Plugins: switch it off and Ask no longer looks up that plugin's records.

### Fixed

- Tax books: a person's own receipts were booked into a book they only keep for someone else, and choosing a default book cleared that flag on other people's books.
- An AI model that kept giving an answer the expected format rejects could hold a worker until the timeout, over and over; each attempt now stops after four model turns. This also made the QA smoke time out since plugins were added.
- A plugin that failed to start showed "Restart to apply"; it now shows why it failed.
- With plugins switched on, new documents waited behind every plugin's work; the worker now takes the document pipeline's jobs first.
- XRechnung invoices now pass the official validator's rules that the first version missed: the business process, the buyer's electronic address, the delivery address for EU supplies, and the date type in a credit note's reference. Issuing an XRechnung invoice needs the customer's mail address.
- The last administrator who can sign in can no longer be demoted or disabled.
- A draft made from a recurring invoice now has its service period, so it can be issued as made.

## [0.9.0] - 2026-11-16

### Added

- **Plugins.** A plugin is a folder you can read and change: it adds document types, screens, background work and questions you can ask, and only does what its declared permissions allow. Switch plugins on under **Settings → Plugins**; change their wording, rules and screens with your own files in `custom/`, which updates never touch. See the [plugin guide](plugins-example/README.md) and [building plugins](plugins-example/BUILDING.md).
- **Five example plugins**, complete enough to use every day:
  - **Tax and bookkeeping for Germany** (`steuer-de`): receipts and e-invoices become bookings you confirm; VAT advance return figures in form order; the income-surplus statement; deadlines; your own invoices with numbers without gaps, issued as a PDF with the e-invoice inside (ZUGFeRD) or as XRechnung, and booked; payments and reminders; letters to the tax office; a hand-over package for your advisor. It calculates; it does not give tax advice. Filing directly through ELSTER is planned.
  - **Bank statements** (`bank`): CAMT, MT940 and CSV statements become payments, matched to your invoices.
  - **Contracts** (`vertraege`): every contract with its cost and last day for notice, and a cancellation letter.
  - **Inventory** (`inventar`): durable goods from receipts, warranties, a contents list and claim bundle for your insurer.
  - **Landlords** (`vermieter-de`): flats and tenancies, the rent ledger and the yearly service-charge statement per tenant.
- **Locked documents.** Issued invoices, closed periods and sent letters cannot be changed or deleted by anyone; an administrator can lift a lock with a reason that stays in the history. Locks survive a rebuild from the vault.
- **Identities** (Settings → Identities): your name, address, tax number and bank account once, for letters and invoices, with an optional mail server to send from.
- **Share by link**: a read-only link to a document for seven days, for someone without an account. Off unless `DOCUHIVE_GUEST_LINKS=true`.
- A **bookkeeper** role: sees what a member sees, plus the categories an administrator assigns.

### Fixed

- Section headings in the sidebar use the same weight as every other heading.

### Security

- Plugins import only `docuhive.sdk`; `docuhive plugins check` refuses anything else. Plugin templates run in a sandbox and PDFs are printed without network access.
- Mail and guest links happen only when a person presses a button; a password is never sent to a mail server without encryption.
- Every view through a guest link is recorded; tokens are stored hashed, links last at most 30 days, and wrong tokens are throttled.

## [0.8.0] - 2026-11-15

### Added

- **An easy way to use DocuHive at home.** `make up LAN=1` serves it over HTTPS to every device on your home network, with no extra account or app; you trust DocuHive's certificate once per device. See the [local network guide](docs/setup/local-network.md). Access from outside the house stays the advanced option ([remote access](docs/setup/remote-access.md)).
- `deploy/scripts/nas.py` finds a NAS on your home network (WD My Cloud, Synology and others), tells you whether it offers NFS or SMB, and writes the systemd units that mount its share as the vault. See the [NAS guide](docs/setup/nas-wd-ex2-ultra.md#find-the-nas-and-write-the-mount).

## [0.7.0] - 2026-11-15

### Added

- The document page shows **Similar documents**, and the dashboard shows suggestions waiting for review, the next deadlines and the state of your mailboxes. Both were built earlier but never displayed.

### Fixed

- **Ask** no longer shows a number of documents as a money total. The table's last row is shown only for a sum, average, lowest or highest value, and says which.
- **Ask** keeps the category, model and **Local only** you choose before your first question. They used to be dropped.
- On a phone, **Analyses** no longer scrolls sideways with a long analysis name, and long card titles wrap. The "then" between a model and its fallback on **AI settings** is readable.

### Security

- AI activity no longer tells an administrator which private document of another member a run was about.
- A cloud model that searches your archive learns only that a restricted document matched: its type and date are withheld too, as its title, sender and text already were.

### Changed

- User journeys E2E-06 to E2E-24 are written. Fifteen run against the real stack: scanner folder, token upload, editing and locks, bulk edit, search, similar documents, Ask totals and citations, privacy across local and cloud-flagged routes, multi-user isolation, quarantine, a storage outage, reminders with the calendar feed, and saved analyses. The three mail journeys wait for mockable provider addresses, and the database-rebuild drill stays on its own stack.

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

[Unreleased]: https://github.com/d2k-klin/docuhive/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/d2k-klin/docuhive/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/d2k-klin/docuhive/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/d2k-klin/docuhive/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/d2k-klin/docuhive/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/d2k-klin/docuhive/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/d2k-klin/docuhive/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/d2k-klin/docuhive/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/d2k-klin/docuhive/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/d2k-klin/docuhive/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/d2k-klin/docuhive/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/d2k-klin/docuhive/releases/tag/v0.1.0

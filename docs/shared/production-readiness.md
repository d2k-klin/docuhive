# Production readiness: plan

**Overview.** What stands between DocuHive 0.5.0 and a 1.0 that a household can trust with its real documents, in the order it has to happen. The status badge changes when the [release gate](../Developer-QA/README.md) says GO, not before: software that has never held a real household's documents on its target hardware is not production software, whatever the label says.

## Where it stands (2026-11-05)

| Area | State |
| --- | --- |
| Platform: settings, database, jobs, worker, sign-in, tokens | Done and verified on PostgreSQL |
| Search, knowledge bases, archive tools (0.2.0) | Done; tested only with synthetic data |
| AI layer, classification, review, mail, Ask, reminders | Built against test doubles; never run with a real provider or mailbox |
| Document intake, vault writes, document service and API | Built in phase 1, including rebuilding the database from the vault; tested with synthetic files on PostgreSQL, Tesseract and Gotenberg |
| Document screens: list, detail, search, upload, quarantine, trash, vocabulary, account, setup checklist, AI run page (0.3.0) | Built and checked in the browser against the real API, worker and OCR with synthetic files; undo, notes and a compact phone menu still open |
| Phone capture and scanner folder | Implemented; production browser and real PostgreSQL checks pass, and the scanner folder runs against the real document core. Real-phone and NAS acceptance pending |
| Production deployment, backups, restore drills | Installed from the installation guide on the production images, with backup, restore, vault rebuild, storage-unavailable and worker-killed drills passing locally ([report](../Developer-QA/reports/local-production-validation-2026-11-05.md)); target NAS/host drills and three nightly backups pending |
| Security checklist, performance targets | Checklist ticked with evidence, OWASP ZAP baseline with no failures; ingest (German and English OCR) and search well under target on the development Mac. Open: both on the target host |
| Release gate | NO-GO until phase 6 |

## Decisions only the owner can make

1. **OCR gate.** Waived by the owner on 2026-11-04; the native core is selected and real-document measurements move to phase 6 ([record](../decisions/0001-ocr-gate.md)).
2. **AI providers.** Which local model host and which cloud keys, so `docuhive ai check` can run for real.
3. **Mail accounts.** Google Cloud and Azure app registrations for Gmail and Outlook sign-in.
4. **Hardware.** The host and NAS the restore and NAS-offline drills run on.

## Phases

Each phase is one or more pull requests with tests, docs and a STATUS update, and each ends usable.

### 1. Document core

The vault (`init`, the availability check, atomic writes with checksum verification, `meta.json` render and rebuild). `ingest.submit` with staging, dedupe, conversion, OCR, thumbnails and quarantine as durable jobs. The documents service (`get`, `get_content`, `apply_metadata`, `iter_ids`, `document.*` events). The document API: list, detail, download, edit, bulk edit, trash and restore.

Done when the contract parity tests run against the real implementation instead of `xfail` (QA-001), and a file uploaded through the API ends `stored` with a searchable PDF/A in the vault.

Progress (2026-11-04): done. Also built: `docuhive vault rebuild` and `vault migrate`, the published `meta.schema.json`, and renaming and merging tags and senders.

### 2. Document screens

Documents list with filters, document detail (preview, metadata editing with AI/user provenance, history), search, drag-and-drop upload, quarantine with retry, vocabulary merge, trash, account settings, and the setup wizard with `/api/system/setup-status` and the dashboard checklist (QA-002).

Progress (2026-11-04): built and checked in the browser against the real API, worker and OCR: documents list with filters and bulk edit, detail with PDF preview, editing, lock badges and unlock, facts and history, search (`/api/search`, falling back to word search when the embedding model is down), upload with live status, quarantine, trash, vocabulary, account settings and the dashboard setup checklist. Still open: undo for edits, notes, a compact navigation on phones.

### 3. Capture

The installable phone capture page (photos, reorder, upload as one document), the polling scanner folder, and API upload with personal tokens (QA-003).

Progress (2026-11-04): capture PWA, EXIF-aware downscaling/rotation/reordering, persistent account-bound offline queue, bounded multipart/token upload, and durable scanner polling are implemented. See the [capture guide](../setup/mobile.md). Scanner originals remain until the stored vault original passes checksum verification. Browser checks use production assets; acceptance on actual phones is still open.

### 4. Operations

`deploy/compose.yml` with API, worker, web, PostgreSQL and the converter: pinned images, non-root, read-only roots, no public ports. A web Dockerfile. NAS mount guide, nightly database dump and restic backup with a timer, documented restore, NAS-offline and restore drills, the library view, and a tested upgrade path between releases.

Progress (2026-11-04): production Compose and standalone web image, NAS/HTTPS guides, quiesced database/vault/staging backups, timer, backup status and warning banner, managed library hardlinks, recovery runbooks and upgrade helper are implemented. A real local restic backup/restore preserved synthetic document bytes, metadata, facts, ownership and staged input. The v0.1.0-to-current schema upgrade passes on disposable PostgreSQL. See the [operations guide](../setup/operations.md) and [drill evidence](../decisions/0003-operations-verification.md). Actual NAS outage, host-loss/vault-only rebuild drills, and three consecutive nightly runs remain pending.

### 5. Hardening

The security checklist ticked item by item (sessions, CSRF, headers and CSP, upload limits, isolated converters, secret handling, log redaction). Performance targets measured: a 1–5 page document ingested in under 60 s, search under 500 ms at 20,000 documents.

Progress (2026-11-04): word search at 20,000 synthetic documents (`make perf-search`, development Mac, PostgreSQL 16 in Docker): median 174 ms, p95 206 ms, max 292 ms. Still to measure on the target host, and with the meaning-based half once an embedding model runs there.

Progress (2026-11-04): the [security checklist](../security-checklist.md) is ticked item by item with its evidence. New: log redaction on every handler, a generated hostile-file corpus through the real pipeline, a permission matrix over every API route, and the host port check in the operations guide. Ingest time (`make perf-ingest`, development Mac, English-only OCR): a scanned 1-page PDF is stored in 4.5 s median (max 4.9 s), a 5-page one in 7.6 s (max 7.7 s), against 60 s. Still open: an OWASP ZAP baseline scan, and both timings on the target host with German and English OCR.

Progress (2026-11-05): on the production images (development Mac, 2 CPUs), German and English OCR stores a 1-page scan in 4.6 s and a 5-page one in 12.8 s. The OWASP ZAP baseline, signed out and signed in, has no failures; its warnings are in the checklist. Two findings are fixed: the calendar feed now needs its own `calendar` token scope, and a restarted worker frees its crashed predecessor's jobs at once instead of after the 30-minute OCR lease. Still open: both timings and the scan on the target host. See the [report](../Developer-QA/reports/local-production-validation-2026-11-05.md).

### 6. Real-world verification and 1.0

Real provider and mailbox runs, a golden evaluation set and the auto-apply gate, the end-to-end journeys, the restore drill on the target hardware, then the QA release gate. On GO: version 1.0.0, and the README badge and status section say so.

## What this plan does not do

It does not mark anything done from mocks, and it does not change the status label before the gate.

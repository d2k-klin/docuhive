# Production readiness: plan

**Overview.** What stands between DocuHive 0.2.0 and a 1.0 that a household can trust with its real documents, in the order it has to happen. The status badge changes when the [release gate](../Developer-QA/README.md) says GO, not before: a document manager that cannot yet store a document is not production software, whatever the label says.

## Where it stands (2026-11-04)

| Area | State |
| --- | --- |
| Platform: settings, database, jobs, worker, sign-in, tokens | Done and verified on PostgreSQL |
| Search, knowledge bases, archive tools (0.2.0) | Done; tested only with synthetic data |
| AI layer, classification, review, mail, Ask, reminders | Built against test doubles; never run with a real provider or mailbox |
| Document intake, vault writes, document service and API | Built in phase 1, including rebuilding the database from the vault; tested with synthetic files on PostgreSQL, Tesseract and Gotenberg |
| Document screens: list, detail, search, upload, quarantine, vocabulary, setup wizard | Not built (QA-002) |
| Phone capture and scanner folder | Not built (QA-003) |
| Production deployment, backups, restore drills | Not built: only dev and test compose files exist |
| Security checklist, performance targets, release gate | Not done; the QA release gate is NO-GO |

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

### 3. Capture

The installable phone capture page (photos, reorder, upload as one document), the polling scanner folder, and API upload with personal tokens (QA-003).

### 4. Operations

`deploy/compose.yml` with API, worker, web, PostgreSQL and the converter: pinned images, non-root, read-only roots, no public ports. A web Dockerfile. NAS mount guide, nightly database dump and restic backup with a timer, documented restore, NAS-offline and restore drills, the library view, and a tested upgrade path between releases.

### 5. Hardening

The security checklist ticked item by item (sessions, CSRF, headers and CSP, upload limits, isolated converters, secret handling, log redaction). Performance targets measured: a 1–5 page document ingested in under 60 s, search under 500 ms at 20,000 documents.

### 6. Real-world verification and 1.0

Real provider and mailbox runs, a golden evaluation set and the auto-apply gate, the end-to-end journeys, the restore drill on the target hardware, then the QA release gate. On GO: version 1.0.0, and the README badge and status section say so.

## What this plan does not do

It does not mark anything done from mocks, and it does not change the status label before the gate.

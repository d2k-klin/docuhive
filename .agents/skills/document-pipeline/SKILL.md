---
name: document-pipeline
description: "Change anything in DocuHive's automatic document flow: sources (email sync/backfill, web upload, PWA capture, consume folder, API token), ingest.submit, OCR/convert, vault writes, quarantine, dedupe, document.* events, classify/extract/embed jobs, periodic schedules and the review queue. Use to keep the pipeline fully automatic, idempotent and lossless, and to make manual uploads get exactly the same analysis and storage as email."
---

# Document pipeline

Once setup is done, DocuHive runs **unattended**: mail is fetched, documents are read, sorted, stored and indexed, and the user is asked only when the AI is unsure. A document uploaded by hand goes through **exactly the same** path and gets the same analysis.

```
email sync/backfill ┐
web upload          ├─► ingest.submit ─► ingest.process (convert → OCR → text → thumb → vault) ─► document.stored
PWA capture         │                        │ failure → quarantine (input kept, retry)                 │
consume folder      │                                                                                   ▼
API token (scripts) ┘                                                             ai.classify → ai.extract → index.embed
                                                                                        │ unsure → review queue
                                                                                        ▼ confident (auto on) → applied
```

## Invariants (never break these)

1. **One entry point.** Every source calls `docuhive.ingest.submit`. No source writes to the vault, the `documents` table or OCR directly.
2. **Lossless.** An input file is deleted only after its vault copy is written **and** its checksum verified. Every failure path keeps the file and records a reason (quarantine, `mail_attachments.status=error`, `consume/_rejected/`).
3. **Idempotent.** Re-running any job or source does no harm:
   - dedupe on `(owner, sha256)` for files and `(account, provider_msg_id)` for mail
   - `dedupe_key`s for per-document jobs
   - the vault rebuild is safe to repeat
4. **Same analysis for every source.** Manual uploads get classify → extract → embed like email. Source-specific knowledge travels only in `IngestRequest.hints` and `SourceInfo` (provenance), never in different code paths.
5. **Unattended.** Every recurring step is a `@periodic` job or an event handler. Nothing requires a user click, except review of low-confidence results, quarantined files, and OAuth re-consent.
6. **Visible.** Every document has a status (`staged → processing → stored | quarantined`) and AI state (suggested, applied, needs review) that the UI shows. Every background job is listed in System → Jobs.
7. **Pausable, not fragile.**
   - NAS down → vault jobs defer, and uploads keep landing in staging.
   - Budget exhausted → bulk AI jobs defer to next month.
   - Provider down → fallback route, or retry with backoff.
   - **No state is lost in any of these.**
8. **Privacy holds on every path** (see the strands-agent-harness skill).

## Procedure: adding or changing a source

1. Write the files to `ingest.incoming_dir()` (same filesystem as staging), then call `submit(files, IngestRequest(owner_id, source=SourceInfo(kind=…), hints=…))`.
2. Store the returned `document_id` in your source's ledger right away. Treat `duplicate` as success.
3. Handle `IngestRejected` (unsupported type, too large) by recording the reason where the user can see it.
4. Never parse document content in the source. That is OCR's and the AI's job. A source may only *pre-filter* using cheap metadata (mime, size, sender, labels).
5. Add the source to the pipeline diagram in `docs/learn/pipelines-and-jobs.md`, and to the setup checks if the user must configure it.

## Procedure: adding a processing step

1. Make it a job with a narrow payload (`{document_id}`) on the right queue: `ocr` for CPU-heavy work, `ai` for model calls, `mail` for provider I/O, `default` for the rest. Give it a `dedupe_key`.
2. Trigger it from an event (`document.stored`, `document.metadata_changed`) or from the previous step. Don't use a cron that scans everything.
3. Make it re-runnable (replace its outputs in one transaction).
4. Raise `RetryLater` for transient errors and `PermanentFailure` for hopeless ones. Use `ctx.defer` for "not now" (vault, budget).
5. Add the step to the document's visible status or the AI panel, so the user sees it happened.

## Manual upload must feel first-class

- Upload, PWA capture and drag-and-drop show live progress, then "Reading text…" → "Classifying…" → the result (title, category, tags) **on the same screen**, with a link to the document and to review if needed.
- The user can set the category and tags at upload time (optional). Those go in as `actor="user"` after ingest, so they are protected from AI overwrite (manual fields).
- Duplicates say "Already in your archive" with a link, not an error.

## Tests (required for pipeline changes)

- Kill the worker mid-step → after restart the document completes, with no duplicates.
- Vault unavailable → staged; available again → stored.
- Same file through two sources → one document. The second gets `duplicate`.
- Quarantine → retry → stored.
- An uploaded document and an emailed document of the same content are classified with the same prompt and route (assert on `ai_runs`).

## Done when

Every source uses `submit`. Every failure keeps the input and shows a reason. Every step is idempotent, event-driven and visible. Manual uploads get the full analysis.

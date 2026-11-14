# QA-03 — Functional verification & E2E journeys (QA-M3)

**Goal:** every user-facing promise works end to end in the real stack, from the user's point of view, on desktop and mobile.

Journeys run on `compose.e2e.yml` (QA-01). AI uses `fake-llm` by default; the nightly `real-ai` profile reruns the AI journeys on Ollama. Each journey is written **ahead** as `test.fixme` (with its blocking milestone in the title), and enabled when the owners mark it done.

## Journey catalogue

| ID | Journey | Requirement IDs | Needs | Joint | Smoke |
|----|---------|-----------------|-------|-------|-------|
| **E2E-01** | First login → setup wizard → "Automation is running" | GUIDE-01, GUIDE-02, GUIDE-03 | OA-M5, CL-M1/M4/M7 steps | J3 | |
| **E2E-02** | Upload a PDF → stored → classified → review → accept | ING-01..03, CLS-01..05, DOC-02 | OA-M3/M5, CL-M2 | J1, J3 | ✅ |
| **E2E-03** | Upload with category and tags set at upload time | DOC-08, CLS-06 | OA-M5, CL-M2 | J3 | |
| **E2E-04** | Phone capture of a 3-page letter (mobile project) | CAP-01, CAP-02, ING-03 | OA-M6 | J3 | |
| **E2E-05** | Capture while offline → queued → uploaded when back online | CAP-01 | OA-M6 | J3 | |
| **E2E-06** | Scanner consume folder, including a half-written file | CAP-03, ING-05 | OA-M6 | J3 | |
| **E2E-07** | API token upload (`upload` scope) cannot list documents | CAP-04, AUTH-02 | OA-M4 | J3 | ✅ |
| **E2E-08** | Edit metadata inline → badge → undo → history → unlock | DOC-03, DOC-07, STO-03 | OA-M5/M7, CL-M2 | J3 | |
| **E2E-09** | Bulk edit 3 documents + undo | DOC-03, DOC-07 | OA-M5 | J3 | |
| **E2E-10** | Search: stemming, accents, typos, filters, hybrid | SRCH-01, SRCH-03, SRCH-04 | OA-M4, CL-M5 | J3 | ✅ |
| **E2E-11** | Similar documents | SRCH-05 | CL-M5 | J4 | |
| **E2E-12** | Ask "How much did I spend on electricity in 2025?" | QA-01..03, QA-07 | CL-M6, OA-M5 | J4 | ✅ |
| **E2E-13** | Ask about one document; "Open as list"; ⌘K entry | QA-07, WEB-05 | CL-M6, OA-M5 | J4 | |
| **E2E-14** | Ask with no results, an ambiguous question, Stop mid-stream | QA-02, QA-07 | CL-M6 | J4 | |
| **E2E-15** | Gmail connect (mock OAuth) → 1-year backfill → rerun → pause/resume | MAIL-01..03, MAIL-06, MAIL-09 | CL-M4 | J2 | |
| **E2E-16** | Outlook (mock Graph) + IMAP (GreenMail) incremental sync, triage | MAIL-02, MAIL-04, MAIL-05, MAIL-07, MAIL-08, MAIL-10 | CL-M4 | J2 | |
| **E2E-17** | Mail token revoked → `needs_reauth` → checklist error → reconnect | MAIL-01, GUIDE-02, GUIDE-04 | CL-M4/M7, OA-M5 | J2 | |
| **E2E-18** | Privacy: restricted documents never reach cloud AI | AI-03, NFR-01 | CL-M1..M6 | J5 | ✅ (S1 class) |
| **E2E-19** | Multi-user isolation everywhere | AUTH-03, QA-06 | OA-M4, CL-M5/M6 | J5 | |
| **E2E-20** | Quarantine: encrypted, unsupported, corrupt → retry/discard | ING-04, ING-06 | OA-M3/M5 | J3 | |
| **E2E-21** | NAS outage during uploads → banner → recovery | STO-05, GUIDE-02 | OA-M3/M7 | J5 | |
| **E2E-22** | DB lost → `vault rebuild` → everything back | STO-04, NFR-03 | OA-M3/M7, CL-M5 (re-embed) | J5 | |
| **E2E-23** | Contract notice deadline → reminder → ntfy + ICS | QA-05, AUTO-03 | CL-M7 | J5 | |
| **E2E-24** | Saved analysis; budget exceeded → local fallback; "How was this made?" | QA-04, AI-04, LRN-03, LRN-04 | CL-M1/M6 | J4 | |

Smoke = runs on every merge to `main`. Everything runs nightly.

## Journey details (key steps → assertions)

**E2E-01 Setup wizard.** Shipped as the dashboard checklist, and the automated journey covers that: every check shows its state and next action, and the state survives a reload ([QA-002](bugs.md#qa-002)). The wizard steps below were not built.
1. Fresh stack, first login as `alice`.
2. The wizard opens: Storage (vault ok) → AI provider (fake-llm as "Local", test connection) → Models (recommended) → Privacy (preset) → Email (connect the mock Gmail) → Phone (a QR code is visible) → Notifications (ntfy-mock, test message received) → Ready.

Assert:
- every `SetupCheck` shows `ok`/`optional`, and the dashboard shows "All set"
- reloading mid-wizard resumes at the same step
- "Skip" works on the optional steps
- breaking the vault afterwards makes the checklist reappear with an `error` and an action

**E2E-02 Upload → review → accept.** Upload `invoice-electricity-2025-11.pdf` and wait for `stored`. Assert:
- the archive has a text layer (`GET /archive` → pdf text contains the invoice number)
- the review item shows category `utilities/electricity` and amount 84.20 EUR
- accepting makes the "You" badges appear
- `meta.json` in the vault holds the accepted values
- the audit log has the entries
- `ai_runs` has classify and extract rows, with `local=true` under the default routing

**E2E-04 Phone capture.** On the mobile project, set input files to 3 JPEGs, one with EXIF orientation 6 (stored sideways), then reorder pages 2↔3 and upload. Assert:
- one document, 3 pages, in the new order
- the page that was sideways is upright: the OCR text of that page contains the expected line
- uploaded image width ≤ 2400 px (checked in a request interceptor)

**E2E-08 Edit, undo, history, unlock.**
1. Change the category via the tree combobox and check the "You" badge.
2. Undo within 8 s → the old value comes back.
3. Change it again, open History → the entries are listed.
4. "Re-run AI" → the field is unchanged and no suggestion overwrites it.
5. "Let AI manage this again" → the next classify changes it (scripted fake-llm answer).
6. Run `library.sync` → a hardlink exists under `library/<new category>/…`, and the original vault path is unchanged (STO-02/03).

**E2E-10 Search.** Query "Rechnungen" finds "Rechnung", "Muller" finds "Müller", "Stadwerke" finds "Stadtwerke". Then: filter by category plus a date range; switch to hybrid, where "letter about pension change" finds the pension letter in the top 5; snippets are highlighted with `<mark>`, with no raw markers or HTML injection (a corpus document contains `<script>` text).

**E2E-12 Ask electricity total.** Send the question, then assert:
- the answer streams (more than one chunk before `done`)
- the `query_facts` table lists the 12 corpus electricity invoices for 2025
- the per-currency total equals the manifest sum (to the cent)
- every invoice is cited, and a citation chip opens the preview
- there is no "uncited" warning
- 👍 is stored

**E2E-15 Gmail backfill.**
1. Connect via the mock OAuth, then backfill 2025-01-01 → 2025-12-31.

   Assert:
   - the progress counters move
   - documents appear with `doc_sources.kind=email` and the provenance fields
   - the newsletters are `triage_rejected` with reasons
   - inline logos are skipped
   - the same attachment in two mails is imported once
2. Rerun the backfill → `imported = 0`.
3. Pause mid-run → the counters stop. Resume → it completes.
4. Kill the worker container mid-run and restart it → it completes with no duplicates.
5. Check that the mock recorded **no** modify or label calls (read-only default, MAIL-08).

**E2E-18 Privacy (S1 class).**
1. Use routing with **only cloud routes** (pointing at `fake-llm` but flagged `local: false`, all through `llm-proxy`).
2. Upload the corpus' medical report, the ID card and the `private`-tagged letter, then trigger classify, extract, embed, chat ("what does my medical report say?") and an analysis.

Assert:
- the proxy log contains **no** request body with any marker string from those documents
- review notices "AI skipped: restricted" exist
- chat shows the "private documents weren't sent" notice
- switching chat to "Local only" (with a local route to `fake-llm` flagged `local: true`) answers with a citation
- `ai_runs` has no row with `restricted=true AND local=false`

**E2E-19 Multi-user isolation.** Bob uploads a private document with a unique marker phrase. As Alice, check every one of these:
- the documents list, FTS, semantic and hybrid search
- similar documents (from Alice's nearest document)
- the chat answer and citations
- reminders and the ICS feed
- `/api/documents/{bob_id}`, `/original`, `/archive`, `/thumb`: all `404`
- the review queue and the triage log

Assert there is no trace of the marker. Then Bob shares the document → Alice can see it but not edit it (PATCH `404`/`403` per the API rules).

**E2E-21 NAS outage.** Run the `nas-toggle` sidecar's "unmount", then upload 3 documents. Assert:
- the banner is shown, and the setup checklist shows `vault` as `error`
- the documents are `staged`, and nothing is written into the bare mount directory (checked from the sidecar)
- after "mount", within 3 min all 3 are `stored` and the banner is gone

**E2E-22 Rebuild.**
1. Snapshot the counts, titles, tags and facts of 30 documents.
2. Drop the DB, run `db upgrade`, then `vault rebuild`.

Assert:
- everything is equal to the snapshot
- after the re-embed jobs, semantic search works again
- manual fields are still manual (a re-classify doesn't touch them)

**E2E-23 Reminders.** Set `DOCUHIVE_TEST_CLOCK` = 2026-11-30. A corpus contract has `end_date` 2027-03-31 and a 90-day notice period. Advance the clock to 2026-12-01 → run `reminders.scan`. Assert:
- ntfy-mock received exactly one "Notice deadline" message, linking to the document
- the ICS feed (token auth) contains a VEVENT on 2026-12-31
- a second scan the same day sends nothing new

**E2E-24 Analyses, budget, learning.**
1. Save the "Utilities spend by month" analysis and run it → a result with a table.
2. Set a tiny Anthropic budget (fake pricing), run chat → a `budget_exceeded` message with a "Use local model" button → it works.
3. Click "How was this made?" on an AI field → the run page shows the route, prompt version (prompt text viewable), output, tokens, cost, and a "Learn about this" link to the correct `docs/learn/` note (the link resolves).

## Manual checks (in `manual-checks.md`, run before each release)

| ID | Check | Why it can't be fully automated |
|----|-------|----------------------------------|
| MC-01 | A real iPhone (Safari, installed PWA) captures over Tailscale away from home | real camera, real network |
| MC-02 | A real Android Chrome capture plus offline Background Sync | real device |
| MC-03 | A real Gmail account: connect, 1-month backfill, token survives longer than 7 days (production-mode GCP app) | real OAuth consent |
| MC-04 | A real Outlook.com account: connect, 1-month backfill | real OAuth consent |
| MC-05 | The real WD My Cloud EX2 Ultra over NFS: vault init, ingest, NAS power-off drill, hardlink library view | real hardware |
| MC-06 | Subscribe to the ICS feed in iOS/macOS Calendar | real client |
| MC-07 | A real ntfy app receives a reminder notification | real client |
| MC-08 | The OCR quality spot check on 10 real documents from the private overlay (owner present) | private data, must not leave the overlay |
| MC-09 | Fresh-install walkthrough by someone who hasn't seen the project, using the wizard and docs only (the GUIDE requirements) | human judgement |

## Functional acceptance per joint milestone

| Joint | QA runs | Report |
|-------|---------|--------|
| J1 | E2E-02 (API-level variant first, the UI variant once OA-M5 lands), I3/I4 checks | `reports/J1.md` |
| J2 | E2E-15, 16, 17, plus MC-03/MC-04 | `reports/J2.md` |
| J3 | E2E-01..10, 20, plus MC-01/MC-02 | `reports/J3.md` |
| J4 | E2E-11..14, 24 | `reports/J4.md` |
| J5 | all E2E twice in a row, all MC, plus [04](04-non-functional.md) | `reports/v1-acceptance.md` |

Each report records: commit SHA, environment, which journeys passed or failed (with links), open defects by severity, and the decision (accepted / accepted with known issues / rejected).

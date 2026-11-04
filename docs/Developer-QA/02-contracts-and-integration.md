# QA-02 — Contracts & integration verification (QA-M2)

**Goal:** prove that OA's and CL's pieces fit together exactly as [contracts.md](../shared/contracts.md) says, and keep them fitting as both tracks move at different speeds.

## 2.1 Contract test suite — `services/docuhive/tests/contracts/`

**Rule:** one test module per contract area. Every test is parametrised over `impl ∈ {fake, real}`. `real` is skipped only while the provider's `STATUS.md` item is unticked, via strict xfail plus the I-item in the reason, never via a plain skip.

| Module | Contract (contracts.md) | Key assertions |
|--------|-------------------------|----------------|
| `test_models.py` | §1 models | JSON round-trip, defaults, `CONTRACT_VERSION`, enum values, and the `SetupCheck` / `MetadataPatch.unlock_fields` / `SearchFilters.document_ids` additions present |
| `test_config.py` | §2.1 | the overlay merge rules (mappings merge, lists and scalars replace), prompt version parsing `name@N`, a broken plugin skipped |
| `test_jobs.py` | §2.3 | dedupe key returns the same id, no-handler stays pending (attempts not consumed), `RetryLater` backoff, `PermanentFailure` → dead, `defer` doesn't count an attempt, the lease reaper, queue isolation (an `ocr` worker never takes `ai`) |
| `test_ingest.py` | §2.4 | ownership of the files (moved), the duplicate returns the existing id, `combine` validation, `UnsupportedType`/`TooLarge` raised synchronously, the `document_id` ULID is assigned immediately, `hints` passed into `document.stored` |
| `test_documents.py` | §2.5 | **every `apply_metadata` rule**: AI skips manual fields unless forced, a user edit adds to manual, `unlock_fields` removes from manual and appears in the event, tags created, correspondent normalised and found, a fact set to None deletes, no event when nothing changed, `meta.json` re-rendered, an audit row written, unknown category ids accepted (OA doesn't validate) |
| `test_auth.py` | §2.6 | `visible_docs` = owner OR shared AND not deleted, admin gets the same rule, the dev bypass is refused outside `ENV=dev`, the trash variant |
| `test_search.py` | §2.7 | hybrid without semantic = FTS order, RRF k=60 with a fake semantic fn, `mode="semantic"` without a fn → error, `document_ids` filter, permissions applied in both lists |
| `test_taxonomy.py` | §3 | `load()` validates, `default_currency`, restricted flags, the fixture equals the default file |
| `test_events.py` | §4 | the payload shape of each event kind, enqueued on queue `ai`, `document.purged` causes CL cleanup |
| `test_routes.py` | §6 | every route in the OpenAPI schema sits under a prefix in the ownership table, the error envelope shape, cursor pagination shape, auth required except the public allow-list |
| `test_setup_status.py` | §6 setup-status | all four endpoints return `list[SetupCheck]`, and required checks have an action |

The `test_contract_drift.py` meta-test:
1. Parses the Python code blocks in `contracts.md`.
2. Compares the class and field names and types with `docuhive.contracts.models` (via `inspect` + `model_fields`).
3. Compares the function signatures with the real modules.
4. Fails on any difference, so the doc and the code can't drift apart.

## 2.2 Boundary enforcement

1. **import-linter** (`.importlinter`, run in `make lint` via a PR to the Makefile touchpoint):
   ```ini
   [importlinter]
   root_package = docuhive

   [importlinter:contract:cl-uses-only-oa-contracts]
   name = CL may import only OA's public contract modules
   type = forbidden
   source_modules = docuhive.ai, docuhive.agents, docuhive.mail, docuhive.taxonomy, docuhive.review, docuhive.index, docuhive.chat, docuhive.reminders, docuhive.notify
   forbidden_modules = docuhive.vault, docuhive.ingest.pipeline, docuhive.ingest.ocr, docuhive.ingest.convert, docuhive.documents.service, docuhive.auth.sessions, docuhive.auth.tokens, docuhive.search.fts
   # allowed (public): docuhive.contracts, docuhive.config, docuhive.db, docuhive.jobs, docuhive.ingest (submit/incoming_dir), docuhive.documents (package API), docuhive.auth (current_user/visible_docs), docuhive.search (hybrid/register_semantic)

   [importlinter:contract:oa-does-not-import-cl]
   name = OA never imports CL internals (only docuhive.ai.startup and docuhive.taxonomy)
   type = forbidden
   source_modules = docuhive.config, docuhive.db, docuhive.jobs, docuhive.worker, docuhive.ingest, docuhive.vault, docuhive.documents, docuhive.auth, docuhive.search, docuhive.api
   forbidden_modules = docuhive.agents, docuhive.mail, docuhive.review, docuhive.index, docuhive.chat, docuhive.reminders, docuhive.notify

   [importlinter:contract:contracts-are-leaf]
   name = contracts depends on nothing in docuhive
   type = forbidden
   source_modules = docuhive.contracts
   forbidden_modules = docuhive.config, docuhive.db, docuhive.ai, docuhive.documents
   ```
   Adjust the module names to what actually exists. The allow-list has to match contracts §2. If the real code needs another public entry point, that is a **contract change**: raise it, don't widen the linter.
2. **Table-write guard:** the system-test trigger from QA-01 §1.3. Plus a static check, `tests/system/test_static_writes.py`: grep CL source for `insert(`, `update(` or `delete(` on core table objects, and for raw SQL `INSERT INTO|UPDATE|DELETE FROM (documents|tags|document_tags|correspondents|doc_facts|doc_sources|notes|users)`. **Exception:** the reads that contracts §5 explicitly allows (reading `doc_facts`, `correspondents`, `jobs`).
3. **Route ownership:** `test_routes.py` above. A new prefix not in the table fails.
4. **Web ownership:**
   - a check that the files under `apps/web/app/(app)/<route>` match the ownership table in contracts §7
   - the slot files exist and export the agreed names
   - `components/intel/*` is imported only by OA's slot locations

## 2.3 Integration point verification (I1–I9)

When the owner ticks an item in their `STATUS.md`, run its checklist on the **real** implementation and record "verified" (with the test names) or "rejected" (with an issue) in [STATUS.md](STATUS.md).

| ID | Verification checklist |
|----|------------------------|
| **I1** skeleton | the package installs, `from docuhive.contracts import *` works, the stub modules have the exact signatures (drift test), `docuhive --help`, health endpoint, CI green |
| **I2** config/db/jobs | `test_config`, `test_jobs` real; two migration envs: `upgrade` from empty creates core then intel, `alembic_version_core` and `alembic_version_intel` both stamped, autogenerate in each env proposes **no** changes to the other's tables; two worker processes never double-process (100 jobs, count = 100) |
| **I3** documents + events | `test_documents` real; `document.stored` emitted exactly once per stored document; a CL handler receives it (system test with the real worker); `metadata_changed` carries `fields` + `unlocked` |
| **I4** ingest | `test_ingest` real; a file submitted by CL's email code (system test via mock-gmail) ends `stored` with `doc_sources.kind=email` and the provenance fields, and CL's `mail_attachments.document_id` equals the result id |
| **I5** auth/search | `test_auth`, `test_search` real; CL's semantic fn registered (`semantic_available=true`), and for a query where Bob's private document is the nearest vector, Alice never gets it in any mode |
| **I6** web shell/proxy | SSE through the proxy arrives incrementally (ticks ~500 ms apart, measured in Playwright), a 50 MB upload streams, the CSRF header is added, a CL page renders inside the shell, nav entries appear |
| **I7** taxonomy | OA's filters show the taxonomy tree from `/api/taxonomy`; the library view uses category labels; the overlay replace behaviour is visible end to end (a custom taxonomy in the e2e overlay changes the filters) |
| **I8** semantic | hybrid ordering differs from FTS-only on the semantic corpus queries, and the search eval targets are met on the synthetic set |
| **I9** slots | each slot renders real content (dashboard widgets, AI panel with runs, similar documents, search hint, setup steps in the wizard), and with CL features disabled (`AI ENABLED=false`) the slots render nothing and nothing errors |

## 2.4 Event-flow and pipeline integration tests — `tests/system/test_pipeline_flow.py`

| Test | Expectation |
|------|-------------|
| upload → stored → classify → extract → embed | the job chain completes; `ai_runs` rows exist for classify and extract; `doc_chunks` exist; review items exist when `auto=false` |
| the same content via upload, consume folder, API token, Gmail mock, Graph mock, IMAP | one document per owner (duplicates reported); the same prompt version and route used for classification (QAR-FN-03) |
| no CL handlers loaded (`AI ENABLED=false`) | documents stored and searchable via FTS; `document.stored` jobs pending with note "no handler", attempts not consumed; after enabling AI they are processed |
| worker killed during `ingest.process` and during `ai.classify` | after restart: completed, no duplicate documents, no duplicate review items |
| re-delivery of `document.stored` (enqueue twice) | dedupe: one classify run |
| `document.purged` | chunks and review items gone, `ai_runs.document_id` null |
| user edit during a running classify | the user value wins (manual field), and the AI suggestion becomes a review item, not an overwrite |
| `unlock_fields` | the next classify may change the field, and the event carries `unlocked` |

## Acceptance (QA-M2)
- The contract suite is complete for every contract section, and green for `fake`. `real` is green for every I-item marked done.
- import-linter, the static write check and the route/web ownership checks run in `make lint` and on `main`.
- The I1–I9 rows in `STATUS.md` are verified (or rejected with issues) within one working session of being ticked.

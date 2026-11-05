# Developer CL — Status

Update this file whenever a milestone or a contract item changes state (working agreement §10).

| Milestone | State | Updated | Notes |
|-----------|-------|---------|-------|
| CL-M0 Spikes: providers + OAuth | not started | 2026-11-04 | Needs real Ollama/cloud keys and Google/Azure app registrations (owner action) |
| CL-M1 AI layer (router, harness, privacy, budgets) | in progress | 2026-11-04 | Code + tests done (FakeModel). Pending: `ai check` against real providers |
| CL-M2 Taxonomy, classify + extract, review queue | in progress | 2026-11-04 | API, pipeline, review UI done. Pending: J1 with OA's real documents service; 20-docs-in-4-min manual test |
| CL-M3 Eval harness + model selection | in progress | 2026-11-04 | Harness, 40-doc synthetic set, FakeModel smoke run done. Pending: golden set, real-model runs, `docs/decisions/0004`, CI `evals.yml` |
| CL-M4 Email ingestion | in progress | 2026-11-04 | Gmail/Graph/IMAP, prefilter, triage, sync/backfill, Sources UI done (fixture-tested). Pending: real OAuth accounts (J2), `docs/setup/mail-accounts.md` |
| CL-M5 Embeddings + semantic search | in progress | 2026-11-04 | Done incl. pgvector integration test. Pending: real embedder, recall targets on a real model |
| CL-M6 Ask agent + chat + analyses | in progress | 2026-11-04 | Agent, tools, SSE, Ask + Analyses UI done. Pending: J4 with a real chat model and OA's `search.hybrid` |
| CL-M7 Reminders, notifications, privacy audit | in progress | 2026-11-04 | Done incl. privacy audit suite. Pending: real ntfy test, calendar subscribe test, `docs/setup/notifications.md` |

## Contract items provided (OA swaps fallbacks for these)
- [x] `docuhive.ai.startup()` exists (2026-11-04)
- [x] I7 `taxonomy.load()` + `config/defaults/taxonomy.yaml` + `services/docuhive/tests/fixtures/taxonomy.yaml` (2026-11-04)
- [x] I8 `search.register_semantic` implementation registered in `startup()` (2026-11-04)
- [x] I9 slots in `apps/web/components/intel/`: `IntelDashboardWidgets`, `DocumentAIPanel`, `SimilarDocuments`, `SearchModeHint`, `intelSetupSteps` (2026-11-04)
- Touchpoints appended: `api/routers.py` (CL_ROUTERS), `worker/handlers.py`, `lib/nav.ts`, `services/docuhive/pyproject.toml` (`ai` extra), root `pyproject.toml` (`evals` workspace member)
- Intel migrations `0002_ai_runs` … `0008_reminders` chain after OA's `0001_intel`; verified on Postgres 16 + pgvector

## Questions for OA
- `manual_fields` / `metadata_changed.fields` naming for facts: CL uses `facts.<name>` (also accepts `facts`). Please confirm.
- Expose `auth.user_for_token(raw, scope)`: the ICS feed currently mirrors the sha256 token hash read-only.
- `ingest.text.extract_text(path)` for PDF golden-set cases.

## Using fallbacks for
- I3/I4 documents/ingest: CL SQLite fakes in `services/docuhive/tests/fakes/intel.py` (OA's are stubs until OA-M3)
- I5 `search.hybrid`: fakes return semantic-only hits; eval `--mode hybrid|fts` waits for OA-M4

## Model selection (CL-M3)
- Decision: _pending_ (needs golden set + real models; see `docs/decisions/0004-model-selection.md`)
- `apply.auto`: **false** until the gate passes

## Mailbox connection experience (2026-11-05)

- Sources now starts with provider selection, prioritises Google/Microsoft sign-in when configured, and shows app-password help or actionable one-time server setup instructions. Custom IMAP servers, separate usernames and folder scope remain available.
- Successful IMAP connections enqueue their first sync after commit, and both IMAP and OAuth connections offer an explicit history range. Import progress and activity refresh while mailboxes are active. Login failures save nothing; server connections have a 20-second timeout.
- Evidence: the intelligence suite passes **164 tests**, with **4 integration tests skipped**. Web unit tests pass **8 tests**; ESLint, TypeScript, focused mypy and Ruff pass. The production Next.js build passes. Synthetic mailbox browser journeys pass **24 checks** at 375/768/1280 in light/dark, including axe, no overflow, failed-login retry, missing configuration and OAuth return. Shared control-height and foundation checks pass **12 tests**. Desktop/light and mobile/dark screenshots were inspected.
- Limits: the UI journeys use synthetic account/source responses, not real provider consent or mailbox fetching. The local Colima instance at localhost:3000 was rebuilt and restarted from this workspace (API, both workers, web); live HTTP health and the deployed mailbox UI bundle pass, and persistent mounts and archive/user row counts are unchanged. Mail encryption is ready; Google/Microsoft app registrations remain unconfigured. `make test-ui` itself is blocked by the host's unaccepted Xcode license; the build and relevant browser checks were run directly. The full docs link checker fails on four pre-existing links inside `.claude/worktrees/feat-archive-tools/tmp/qa/uv-cache`; changed documentation links are valid.

## Category choices and visible AI progress (2026-11-05)

- Administrators can enable predefined categories and add custom ones in Vocabulary. Classification receives only enabled choices; the full taxonomy retains disabled categories and their privacy restrictions. Database preferences are read fresh by API and workers, and a setup check links to category choices.
- A permission-scoped batch endpoint derives current progress from queue records, AI runs and pending review. Re-runs supersede previous completion, failed extraction is not reported as successful completion, and a category suggestion is not reported as applied. Uploads, document tables, saved groups and document details poll real status. The detail panel exposes category acceptance and the existing run trace.
- Evidence: **362 service tests**, **10 web unit tests**, **4 learning examples**, **30 browser checks** and the 40-case FakeModel oracle gate pass; deliberately noisy category outputs fail their gate as expected. Builds, lint, type checks and 118 changed-document links pass. Learning note/example 02 and note 12 explain the choices and progress model.
- The local Colima instance is running the new images, with storage mounts and all seven documents/two users preserved. Live read-only checks return 35 categories and seven `needs_review` documents. Real-model accuracy for custom categories remains unmeasured; no existing document was automatically reclassified.

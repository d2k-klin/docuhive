# Developer OA — Status

Update this file whenever a milestone or a contract item changes state (working agreement §10).

| Milestone | State | Updated | Notes |
|-----------|-------|---------|-------|
| OA-M0 Repo skeleton + contract stubs + CI | in progress | 2026-11-03 | Workspaces, exact contract models, stubs, CLI, health, CI and contributor tooling implemented; local build/checks passing, CI publication unverified. |
| OA-M1 OCR spike + gate | in progress | 2026-11-03 | Isolated spike, conversion/OCR primitives, synthetic generator and CER tool implemented. Private corpus and target-host measurements unavailable; gate pending. |
| OA-M2 Platform (settings, overlay, DB, jobs, worker) | in progress | 2026-11-03 | Settings/overlay/plugins, core schema, separate migration environments, jobs/worker/scheduler and contract fakes implemented; real PostgreSQL checks underway. |
| OA-M3 Ingest pipeline, vault, documents service | not started | 2026-11-03 | |
| OA-M4 Auth, API, FTS + hybrid search | in progress | 2026-11-03 | Independent auth portion implemented: passwords, sessions, scoped tokens, CSRF, rate limits, user operations and visibility SQL. Document API/search await OA-M3. |
| OA-M5 Web shell + document UI | in progress | 2026-11-03 | Web scaffold, tokens, navigation, generated API types and streaming BFF implemented. Archive workflows and complete shell remain pending. |
| OA-M6 PWA capture + consume folder | not started | 2026-11-03 | |
| OA-M7 Ops: compose, NAS, backups, drills | not started | 2026-11-03 | |
| OA-M8 Hardening + cloud profile | not started | 2026-11-03 | |

## Contract items provided (CL swaps fallbacks for these)
- [x] I1 skeleton, `contracts/models.py`, stub modules (2026-11-03; local model/contract checks pass)
- [ ] I2 `config.load_yaml/prompt/plugins`, `db.session`, intel Alembic env, `jobs.*`
- [ ] I3 `documents.get/get_content/apply_metadata/iter_ids`, `document.*` events
- [ ] I4 `ingest.submit/incoming_dir`
- [ ] I5 `auth.current_user/visible_docs`, `documents.get_for_user`, `search.hybrid/register_semantic`
- [ ] I6 web shell, BFF proxy (SSE verified), generated API client, slot placeholders

## Using fallbacks for
- I7 `taxonomy.load()`: fixture `tests/fixtures/taxonomy.yaml`
- I8 semantic search: FTS-only
- I9 slot components: `null` placeholders

## Gate result (OA-M1)
- Decision: **pending** ([gate record](../decisions/0001-ocr-gate.md)). The user confirmed no private corpus or reference transcriptions are available. Do not infer GO or NO-GO from synthetic checks.

## Current verification

- 42 OA unit/contract/documentation/example checks pass without keys or network.
- OA runtime modules pass Ruff and mypy checks; the Next.js production build passes.
- Four web logic tests pass, including streaming SSE, streamed upload forwarding and cross-site rejection.
- Full available unit suite: 145 passed, one CL startup failure while that track is still adding mail handlers. CL files were not changed to address it.
- Docker storage exhausted during initial test-image pulls. Authorized unused-image/cache cleanup reclaimed 46 GB; the isolated test stack is being retried.
- Synthetic native OCR smoke preserves born-digital text and processes a generated scan; this is **not** real-corpus gate evidence.

## Next dependency

Finish actual PostgreSQL and conversion-service checks for OA-M2 and spike tooling.
The selected archive implementation (OA-M3), document workflows and deployment
acceptance remain dependent on the measured OA-M1 backend decision.

# Developer QA — Status

Update this file whenever a milestone, a verification or a blocker changes state.

| Milestone | State | Updated | Notes |
|-----------|-------|---------|-------|
| QA-M0 Strategy, traceability, bug process | in progress | 2026-11-04 | Generator lists all 127 product/QA IDs; manual register and local issue process exist. Remote labels/issues not created. |
| QA-M1 System test harness (stack, corpus, mocks, CI) | in progress | 2026-11-14 | Isolated HTTPS stack builds and starts with real OCR (QA-010) and restarts killed services; separate contract/system DBs; 150 deterministic files / 15 cases; capturing HTTP fixtures; pinned workflows. Mail/real-AI profiles and remote CI pending. |
| QA-M2 Contracts & integration verification | in progress | 2026-11-14 | Model/signature drift, document/ingest parity and boundary checks pass on the real implementation; all three import contracts kept (QA-004 fixed). |
| QA-M3 Functional & E2E journeys | in progress | 2026-11-14 | Login/logout, E2E-01…05 and incremental SSE pass on 375/768/1280 px in light/dark against the real API, worker, OCR and scripted AI. E2E-06…24 are not written. |
| QA-M4 Non-functional verification | in progress | 2026-11-04 | Default suite: 309 passed, 85.34% lines. Implemented critical modules ≥95%. Real SQL permission/decimal checks and 25-asset bundle scan pass. Browser: 18 pass, 54 font failures, 30 pending. Vault, full security/privacy, hardware/drills/upgrade/mutation pending. |
| QA-M5 Release gate | blocked (product prerequisites) | 2026-11-04 | Gate implemented; v1 NO-GO. No real archive acceptance, manual signatures or reference-host evidence. |

## Integration points (verified on the real implementation)

| Item | Implementation observed | QA verdict | Evidence / issue |
|------|-------------|------------|------------------|
| I1 skeleton + contracts | Package, models, CLI and API available | Locally verified; remote CI pending | Contract drift suite; production image build; real health/version |
| I2 config/db/jobs | Real PostgreSQL and durable worker available | Partially verified | Core/intel migrations, dedupe/leases, kill/recovery; 25 existing integration tests pass. Cross-track import issue QA-004 remains. |
| I3 documents + events | Public document functions are stubs | Not ready | Three real document parity xfails; QA-001 |
| I4 ingest | Public ingest functions are stubs | Not ready | Two real ingest parity xfails; QA-001 |
| I5 auth/search | Auth real; hybrid search stub | Auth verified, search pending | Real API scopes/sessions; PostgreSQL + independent SQL visibility matrix; QA-001 |
| I6 web shell/proxy | Production web/BFF available | Partially verified | Six-project login/logout + incremental SSE pass; large upload pending |
| I7 taxonomy | Real loader and setup checks available | Partially verified | Schema/drift/default suites pass; OA filter/library integration pending |
| I8 semantic | CL modules available; OA hybrid stub | Not verified end to end | QA-001; no real archive to index |
| I9 slots | Host document/wizard surfaces incomplete | Not verified | Dashboard/document/search/setup integration still pending |

## Joint milestones

| Joint | State | Report |
|-------|-------|--------|
| J1 First classified document | not ready | |
| J2 Email to archive | not ready | |
| J3 Daily use | not ready | |
| J4 Ask | not ready | |
| J5 v1 | not ready | |

## Open S1/S2 defects

[QA-005](bugs.md#qa-005) is open: provider endpoints cannot be pointed at the mocks, so mail
and privacy paths are not proven end to end. QA-001…004, 006…011 are fixed and verified
(2026-11-14). No S1 incident has been reproduced. The integration-point and joint-milestone
tables above date from 2026-11-04 and have not been re-run.

## Notes
- Requests to OA/CL for testability (mock base URLs, `base_url` per provider, test clock, `application_name` per module) are still to be opened as `contract` issues (QA-01 §1.1, §1.3).
- Native `make` is blocked on this host by the Xcode licence prompt. Equivalent commands ran directly; no licence acceptance or machine configuration was changed.
- Evidence and remaining scope: [execution plan](EXECUTION_PLAN.md), [verification](reports/initial-verification.md), [audit](reports/test-audit-2026-11-04.md), [traceability](traceability.md).

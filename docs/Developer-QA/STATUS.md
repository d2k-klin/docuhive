# Developer QA — Status

Update this file whenever a milestone, a verification or a blocker changes state.

| Milestone | State | Updated | Notes |
|-----------|-------|---------|-------|
| QA-M0 Strategy, traceability, bug process | in progress | 2026-11-04 | Generator lists all 127 product/QA IDs; manual register and local issue process exist. Remote labels/issues not created. |
| QA-M1 System test harness (stack, corpus, mocks, CI) | in progress | 2026-11-04 | Isolated stack builds and starts; 150 deterministic files / 15 cases; provider/mail mocks; pinned smoke/nightly workflows. Verifying HTTPS system/browser paths. Full corpus and mail/real-AI profiles pending. |
| QA-M2 Contracts & integration verification | in progress | 2026-11-04 | Model/signature drift, document/ingest parity and boundary checks implemented. Real archive paths remain OA stubs. Boundary violation QA-004 recorded. |
| QA-M3 Functional & E2E journeys | in progress | 2026-11-04 | Real login and initial UI checks; E2E-01…05 test-ahead skeletons. Remaining journeys await real product paths. |
| QA-M4 Non-functional verification | in progress | 2026-11-04 | Default sockets blocked; coverage first measured 85.01%; axe/layout checks, benchmark and signed-evidence gates exist. Critical coverage, security/privacy matrix, hardware/drills/upgrade/mutation pending. |
| QA-M5 Release gate | blocked (product prerequisites) | 2026-11-04 | Gate implemented; v1 NO-GO. No real archive acceptance, manual signatures or reference-host evidence. |

## Integration points (verified on the real implementation)

| Item | Owner state | QA verdict | Evidence / issue |
|------|-------------|------------|------------------|
| I1 skeleton + contracts | OA: done (2026-11-03) | **to verify** | |
| I2 config/db/jobs | OA: in progress | — | |
| I3 documents + events | OA: not started | — | |
| I4 ingest | OA: not started | — | |
| I5 auth/search | OA: in progress (auth part) | — | |
| I6 web shell/proxy | OA: in progress | — | |
| I7 taxonomy | CL: not started | — | |
| I8 semantic | CL: not started | — | |
| I9 slots | CL: not started | — | |

## Joint milestones

| Joint | State | Report |
|-------|-------|--------|
| J1 First classified document | not ready | |
| J2 Email to archive | not ready | |
| J3 Daily use | not ready | |
| J4 Ask | not ready | |
| J5 v1 | not ready | |

## Open S1/S2 defects

[QA-001…005](bugs.md) track archive/setup/capture prerequisites, private settings imports,
and missing endpoint/clock/write-origin test hooks. No S1 incident has been reproduced.
QA-006 records the integration skip-policy gap (S3).

## Notes
- Requests to OA/CL for testability (mock base URLs, `base_url` per provider, test clock, `application_name` per module) are still to be opened as `contract` issues (QA-01 §1.1, §1.3).

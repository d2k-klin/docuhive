# Initial QA verification

2026-11-04 · development checkout, not a frozen release candidate.

Decision: **NO-GO for v1**. QA's runnable foundation is implemented; the full
QA-M0…M5 acceptance programme remains incomplete. No OA/CL documents or production
code were changed. Their unfinished contracts were exercised and recorded as
dependencies, not replaced with fake product behaviour.

Candidate source fingerprint:
`f1af7bc56913eeea3ff9d9183c1ed7c4f6915cc89770a7745b5be48ef20e636c`.
The evidence store matches this fingerprint. Generated Next type imports are
excluded, while application source, tests, contracts, config and lockfiles are hashed.

## Measured results

| Check | Result |
| --- | --- |
| Default Python, sockets blocked | **309 passed**, one strict expected private-import failure, 43 integration cases deselected |
| Overall service line coverage | **85.34%**, above the existing 85% gate |
| Contracts plus existing real PostgreSQL/platform suites | **52 passed**, five strict expected archive-contract failures |
| Live API system suite | **6 passed**, two strict expected failures: upload and storage setup-status |
| Browser, six width/theme projects | **18 passed**, **54 failed**, **30 pending** |
| Browser successes | Login/member boundary/logout, incremental SSE through the BFF, production rejection of the development page |
| Browser failures | Shared Inter/Times font defect on nine static production pages × six projects; QA-009 |
| Browser pending | E2E-01…05 skeletons × six projects; these do not count as accepted journeys |
| Web unit suite | **6 passed** |
| Lint and types | Ruff/format: 191 files; mypy: 101 source files; ESLint and strict QA TypeScript checks pass |
| Real provider transport smoke | Strands triage and embeddings → capturing HTTP proxy → scripted backend; real `ai_runs` rows |
| Built-browser scan | **25 assets**; no source maps, configured prompt lines or server provider variables found |
| Python AGPL gate | Passed |
| Traceability | **127 IDs**: 12 passing linked checks, 38 pending, two failing, 75 without links |
| Strict traceability, drill evidence and release gates | Correctly reject the incomplete candidate |

The browser sweep uses real authenticated requests, not intercepted API responses.
It checks the initial seeded states; dynamic run detail, loaded archives, error/dialog
states, manual keyboard journeys and approved visual baselines remain pending.
The real PostgreSQL run independently exercised migrations, dedupe, leases,
worker kill/recovery and authentication. SQLite tests additionally exercise the
actual permission and fact-query functions with owner/admin/private rows and
per-currency decimal sum/average/min/max, including missing numeric values.

## Critical coverage

| Module | Lines |
| --- | --- |
| Fact validators | 100.00% |
| Fact aggregation | 98.31% |
| Privacy routing | 95.83% |
| Permission predicates | 100.00% |
| Metadata mutation | 98.25% |

The critical gate still fails for the absent vault implementation. The real ingest,
document and hybrid-search entry points remain stubs; their coverage cannot prove
dedupe, durable storage or user-edit protection. Mutation testing has not run.

## Harness and artifacts

The stack builds the real API/workers and production Next app, reusing the existing
Postgres/Gotenberg services. Product services are on an internal Docker network;
a fixed-destination gateway provides localhost HTTPS. Contract resets use
`docuhive_contract_test`, separate from the seeded system DB. TLS is disposable QA
material under ignored `tmp/qa/tls`, and was not installed in the host trust store.

The corpus generator produces 150 deterministic files across 15 logical cases,
with PDFs, scans, EXIF-oriented JPEGs, HEIC, Office, text, HTML and email. It is
synthetic and cannot satisfy the real OCR-quality or reference-host gate. A full
regeneration produced the same hashes; manifest fact names match the invoice taxonomy. Current
HTTP scripts and mail fixtures are a starting subset, not the full QA-M1 corpus or
mail/provider matrix. OCR system binaries and the real mail/AI profiles remain pending.

Reproduction commands are the `qa-*` targets in the root Makefile; the underlying
commands were run directly here because native `make` stops at this host's Xcode
licence prompt. No licence acceptance or host configuration was changed.

Raw logs, captures, coverage, browser measurements, screenshots and traces are
under ignored `tmp/qa/`. Permanent coverage intent is in [traceability](../traceability.md).
Remote workflows have not run; GitHub issues/labels have not been published.

## Remaining acceptance

See [execution plan](../EXECUTION_PLAN.md), [status](../STATUS.md) and
[defects](../bugs.md). Real archive/search contracts, I1–I9 completion, E2E-06…24,
all-path privacy, authz/fuzz/ZAP, full mail/OAuth/IMAP/SMTP replay, real providers,
reference-host performance, visual approval, mutation, upgrades, NAS/restore drills,
manual signatures and OA/CL acknowledgement still prevent release sign-off.

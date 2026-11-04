# QA — Requirements

Status: draft v0.1 · 2026-11-04 · applies to [../REQUIREMENTS.md](../REQUIREMENTS.md) v0.3

These are the requirements on the **QA track itself**: what must be verified, how, and when a build counts as good enough.

## 1. Scope

In scope:
- the whole system: Python API and worker, Next.js web, Postgres, Gotenberg, OCR, the vault on a NAS-like mount, AI providers (fake, local Ollama, one cloud provider), mail providers (mocked and one real test account), and the deployment profiles (local, home host, cloud)
- the integration between OA and CL
- the quality of the OA and CL test suites

Out of scope: the WD NAS firmware itself, provider uptime, and legal review.

## 2. Requirements

### 2.1 Traceability (QAR-TR)
- **QAR-TR-01** Every requirement ID in `REQUIREMENTS.md` (STO, ING, MAIL, CAP, DOC, CLS, SRCH, QA, AUTH, AI, WEB, EXT, AUTO, LRN, GUIDE, NFR) maps to at least one automated test, or a documented manual check, in `docs/Developer-QA/traceability.md`.
- **QAR-TR-02** Test names or markers carry the requirement IDs (`@pytest.mark.req("STO-04")`, and Playwright `test("… @STO-04")`). `make qa-trace` regenerates the matrix and lists the uncovered IDs.
- **QAR-TR-03** No requirement counts as "accepted" at the release gate without a passing linked test or a signed manual check (date, environment, result).

### 2.2 Contracts & integration (QAR-INT)
- **QAR-INT-01** Every function, event, model and route in `docs/shared/contracts.md` has a contract test that runs against the **real** implementation, and against the fake where one exists (same assertions, parametrised).
- **QAR-INT-02** Each integration point I1–I9 has a verification checklist. QA marks it verified only when its checks pass on the real implementations.
- **QAR-INT-03** The track boundaries are enforced automatically:
  - CL code never imports OA-private modules, and the reverse (import-linter)
  - no writes to the other track's tables (static check plus a runtime guard in system tests)
  - route prefixes match ownership
  - web slot files exist and render
- **QAR-INT-04** The event chain `document.stored → classify → extract → embed` (and `metadata_changed`, `quarantined`, `trashed`, `purged`) is verified end to end with a real worker, including "no handler yet" behaviour and idempotent re-delivery.
- **QAR-INT-05** The two Alembic environments upgrade from empty and from the previous release, in order (core then intel), without touching each other's tables.

### 2.3 Functional (QAR-FN)
- **QAR-FN-01** The user journeys E2E-01…E2E-24 ([03-functional-and-e2e.md](03-functional-and-e2e.md)) are automated against the full stack, and run on every merge to `main` (the smoke subset) and nightly (all of them).
- **QAR-FN-02** Every joint milestone J1–J5 has an acceptance run recorded in `docs/Developer-QA/reports/`.
- **QAR-FN-03** Each source (upload, PWA, consume folder, API token, email: Gmail mock, Graph mock, IMAP) produces the same document analysis for the same content (the document-pipeline invariant 4).
- **QAR-FN-04** Each AI provider kind that is supported (fake, Ollama, at least one cloud provider) passes a provider smoke suite (classify, extract, embed, chat), run nightly or on demand. Copilot runs only if it is enabled.

### 2.4 Non-functional (QAR-NF)
- **QAR-NF-01 Privacy:** no restricted document's content reaches a non-local provider, on any path (classify, extract, embed, triage, chat, analyses, evals). This is verified by a capturing proxy in system tests in addition to CL's unit audit.
- **QAR-NF-02 Security:**
  - the OA-M8 checklist is verified independently
  - an OWASP ZAP baseline scan of the web app finds no high or medium issues
  - authorisation matrix tests for every route (owner, other user, admin, token scopes)
  - the upload fuzz corpus does not crash the worker
- **QAR-NF-03 Performance:**
  - search p95 < 500 ms at 20k documents
  - ingest of a 1–5 page document < 60 s on the reference host
  - chat first token < 5 s (cloud)
  - the UI's Largest Contentful Paint < 2.5 s on `/documents` (local)
- **QAR-NF-04 Accessibility:** axe reports no violations on every page in light and dark, and keyboard-only completion of E2E-02, E2E-08, E2E-10 and E2E-12.
- **QAR-NF-05 UI consistency:** on **every** page (not only `/dev/ui`):
  - all controls are 36 ± 0.5 px (or the sm/lg tokens where allowed)
  - no heading is larger than 20 px
  - one font family
  - no horizontal overflow at 375/768/1280 px
  - screenshots taken in light and dark, compared to approved baselines
- **QAR-NF-06 Resilience:** the drills (NAS down, worker killed mid-job, DB lost → vault rebuild, provider down, budget exceeded, mail token revoked) are automated where possible and run before each release.
- **QAR-NF-07 Upgrade:** upgrading from the previous release (DB migrations plus `meta.json` schema) keeps every document, its metadata and search results.
- **QAR-NF-08 Public-repo hygiene:**
  - no secrets (gitleaks)
  - no real data (a fixture scan for IBAN, email or phone patterns outside the synthetic allow-list)
  - no source maps or prompts in the web bundle
  - licence check passes
  - commits authored only by the repo owner
- **QAR-NF-09 Docs & learning:** every relative link resolves, every `examples/learn` example runs with FakeModel, and every setup doc linked from the UI exists.

### 2.5 Test quality (QAR-TQ)
- **QAR-TQ-01** The default suites (`make test`) are hermetic: no network (enforced with `pytest-socket`, allowing only localhost for integration markers), no API keys, deterministic.
- **QAR-TQ-02** The coverage gate is ≥ 85% lines on `services/docuhive`. Critical modules (validators, money/date parsing, privacy, permissions, `apply_metadata`, dedupe, vault atomic write) are at ≥ 95% lines, **and** survive mutation testing (mutmut on those modules, run nightly, ≥ 80% killed).
- **QAR-TQ-03** Flaky tests are detected (nightly rerun of failures, flake log) and fixed or quarantined with an issue within one week. A test is never retried silently in CI.
- **QAR-TQ-04** No test is skipped or xfailed without a linked issue, and xfails are `strict=True`.
- **QAR-TQ-05** Every fixed bug gets a regression test that failed before the fix.

### 2.6 Defects (QAR-BUG)
- **QAR-BUG-01** Every defect gets a GitHub issue with a severity (S1–S4), an area (`bug:oa` / `bug:cl` / `bug:integration`), the reproduction steps, and a failing test whenever possible.
- **QAR-BUG-02** S1 is data loss, a privacy leak, a security hole, a wrong number or a fabricated citation in an answer, or a lost user edit. It blocks merges in the affected area and blocks any release.
- **QAR-BUG-03** QA fixes bugs directly only within the fix policy ([05](05-test-audit-bugs-and-release.md#53-fix-policy)). Everything else goes to the owner with the failing test attached.

## 3. Quality gates

| Gate | When | Must pass |
|------|------|-----------|
| **PR** (owned by OA/CL CI) | every PR | lint, unit and contract tests, coverage, gitleaks, licence check, link check |
| **Main smoke** (QA) | every merge to `main` | system stack up, E2E smoke (E2E-01, 02, 07, 10, 12), boundary checks |
| **Nightly** (QA) | 02:00 UTC | all E2E, provider smoke (Ollama), perf benches, ZAP baseline, mutation testing (critical modules), flake rerun, a11y and visual on all pages |
| **Joint milestone** J1–J5 | when both sides are done | the journeys listed for that milestone, plus the non-functional items in scope, with a report written |
| **Release** (QA-M5) | before a `v*` tag | everything above, plus drills, upgrade test, traceability 100%, zero open S1/S2 |

## 4. Exit criteria for v1 (QA sign-off)

- [ ] Traceability: 100% of requirement IDs covered, all passing or signed manual checks.
- [ ] Contracts: all contract tests green against the real implementations, and I1–I9 verified.
- [ ] E2E-01…E2E-24 green twice in a row on the reference host.
- [ ] Non-functional QAR-NF-01…09 green.
- [ ] Test-quality QAR-TQ-01…05 green.
- [ ] No open S1 or S2 issues. S3 issues are triaged with an owner and a milestone.
- [ ] Sign-off report `docs/Developer-QA/reports/v1-acceptance.md`, written by QA and acknowledged by OA and CL.

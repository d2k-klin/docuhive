# Developer QA — Verification, integration & quality track

You own **whether DocuHive actually works, as one product**. OA builds the platform and CL builds the intelligence and connectors. You check:
- that the pieces fit (the contracts and integration points I1–I9)
- that every requirement does what it promises (functional and end-to-end)
- that the other developers' tests are trustworthy
- that the non-functional promises hold (privacy, security, performance, accessibility, resilience, UI consistency)

When something is wrong, you **prove it with a failing test and get it fixed**, either by fixing it yourself (within the fix policy) or by handing a reproducible issue to the owner.

## Project in one paragraph

DocuHive is a self-hosted, open-source, AI-first document hub. Documents arrive by email, phone camera, scanner or upload. They are OCR'd and stored in a self-describing vault on a WD NAS, classified by AI into a controlled taxonomy, and made searchable and askable with local or cloud AI, behind a privacy gate. It is also a learning project for Strands agents and agent harnesses. Stack: Python (FastAPI, worker, Strands) + Next.js, with Postgres (FTS + pgvector), OCRmyPDF and Gotenberg.

## Read first

1. [../REQUIREMENTS.md](../REQUIREMENTS.md): every requirement ID is something you must be able to point a test at
2. [../IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md)
3. [../shared/README.md](../shared/README.md), [../shared/contracts.md](../shared/contracts.md), [../shared/working-agreement.md](../shared/working-agreement.md)
4. [../Developer-OA/README.md](../Developer-OA/README.md) and [../Developer-CL/README.md](../Developer-CL/README.md), and both `STATUS.md` files: **your work queue is driven by what they mark done**
5. The skills, especially [`lessons-learned`](../../.agents/skills/lessons-learned/SKILL.md) (your checklist of things that went wrong before), [`docuhive-ui`](../../.agents/skills/docuhive-ui/SKILL.md), [`guided-experience`](../../.agents/skills/guided-experience/SKILL.md), [`document-pipeline`](../../.agents/skills/document-pipeline/SKILL.md), [`document-editing`](../../.agents/skills/document-editing/SKILL.md), [`document-chat`](../../.agents/skills/document-chat/SKILL.md) and [`strands-agent-harness`](../../.agents/skills/strands-agent-harness/SKILL.md)

## Files in this folder

| File | What it is |
|------|------------|
| [00-requirements.md](00-requirements.md) | What QA must guarantee (QAR-* requirements), quality gates, exit criteria |
| [01-strategy-and-harness.md](01-strategy-and-harness.md) | QA-M0 strategy + traceability; QA-M1 system test harness (stack, corpus, mocks, CI) |
| [02-contracts-and-integration.md](02-contracts-and-integration.md) | QA-M2: contract tests, boundary enforcement, I1–I9 verification, event flows |
| [03-functional-and-e2e.md](03-functional-and-e2e.md) | QA-M3: user journeys E2E-01…E2E-24 mapped to the joint milestones J1–J5 |
| [04-non-functional.md](04-non-functional.md) | QA-M4: privacy, security, performance, accessibility, UI consistency, resilience, upgrade, public-repo hygiene |
| [05-test-audit-bugs-and-release.md](05-test-audit-bugs-and-release.md) | Auditing OA/CL tests, bug triage, fix policy, QA-M5 release gate |
| [STATUS.md](STATUS.md) | Your progress, verified integration points, open blockers |

## Your milestones

| Milestone | Can start | Depends on (fallback: write the test ahead as strict `xfail`) |
|-----------|-----------|----------------------------------------------------------------|
| **QA-M0** Strategy, traceability matrix, bug process | now | — |
| **QA-M1** System test harness: e2e stack, synthetic corpus, mocks, CI | now | OA-M0 skeleton (it exists) |
| **QA-M2** Contracts & integration verification | when OA-M2 is done; then per I-item | each I1–I9 marked done |
| **QA-M3** Functional & E2E journeys | per joint milestone J1–J4 | OA/CL milestones per journey |
| **QA-M4** Non-functional verification | partly now (hygiene, a11y on existing pages); the rest per feature | features in place |
| **QA-M5** Release gate (J5 v1 acceptance) | when all OA/CL milestones are done | everything |
| **Continuous** Test audit, bug triage and fixing | from day 1 | — |

**Estimated effort:** about 8–10 part-time weeks spread alongside the others (M0 0.5 · M1 1.5 · M2 1.5 · M3 3 · M4 2 · M5 1, plus continuous triage).

## How you work with the other two at different paces

- **Test ahead, never wait.** Write the test for a feature before it lands, marked `@pytest.mark.xfail(strict=True, reason="waiting OA-M3 / I3")` (Playwright: `test.fixme` + an issue link). When the feature lands and passes, the strict xfail turns red, which is your signal to remove the marker. Nothing silently stays skipped.
- **Verify what is marked done.** When OA or CL ticks a milestone or an I-item in their `STATUS.md`, run your verification for it (within one working session of noticing). Record the result in your `STATUS.md` as **verified** (with the test names) or **rejected** (with the issue link). A "done" that QA rejected goes back to "in progress" in the owner's STATUS.
- **Test real implementations, not fakes.** Fakes are for the developers' unit tests. QA's contract and system tests run against the real implementation as soon as it exists, and they assert that the fake and the real implementation behave the same.
- **Don't block daily work.** QA gates only the joint milestones (J1–J5) and releases, never individual PRs. The exception is a new S1 bug (data loss, privacy leak, security hole, wrong numbers in answers), which blocks merges in the affected area until it is fixed.

## Skills to load

[`lessons-learned`](../../.agents/skills/lessons-learned/SKILL.md) (always), [`repo-structure`](../../.agents/skills/repo-structure/SKILL.md) (your new folders and workflows), and the feature skills listed above when verifying that area. See the working agreement §13.
# Running the current harness

The current [execution plan](EXECUTION_PLAN.md) separates runnable verification from
dependency-bound acceptance. All QA-M0…M5 tasks remain governed by the numbered plans.

Use `make qa-check qa-corpus qa-up qa-contracts qa-system qa-e2e qa-trace`.
`make qa-down` removes only the `docuhive-qa` stack and its volumes. The QA
contract database is separate from the seeded system database.
`make qa-trace QA_TRACE_ARGS=--strict` and `make qa-release` fail until current
acceptance evidence is complete. `make qa-boundaries` exposes known ownership
violations without hiding them in an allow-list.

Implementation evidence and remaining work live in [STATUS.md](STATUS.md),
[bugs.md](bugs.md), [manual-checks.md](manual-checks.md) and [reports](reports/README.md).

`qa-up` creates a disposable localhost TLS key under ignored `tmp/qa/tls`, used
only for this test stack. Python verifies that certificate; Playwright accepts it
only within the QA configuration. `qa-provider-smoke` checks real Strands/HTTP and
`ai_runs`. `qa-audit` enforces overall and critical coverage; `qa-bundle` scans
the built browser assets. `qa-nightly` attempts all available suites even if one
fails. Ollama/cloud, IMAP/SMTP, full security/mutation and all recovery drills
are still pending and are not silently reported green.

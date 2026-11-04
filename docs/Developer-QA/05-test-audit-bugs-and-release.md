# QA-05 — Test audit, bug triage & fixing, release gate (continuous, QA-M5)

## 5.1 Auditing OA's and CL's tests (QAR-TQ)

Run the audit at each OA or CL milestone marked done, and weekly on `main`. Record the findings in `reports/test-audit-<date>.md`.

| Check | How | Fail → |
|-------|-----|--------|
| Hermetic default suite | add `pytest-socket` (`--disable-socket --allow-hosts=127.0.0.1,localhost` only for `integration`); run `make test` with the network off (`unshare -n` or Docker `--network none`) | S2 issue to the owner: the test that touched the network |
| No keys needed | run `make test` with an empty env (`env -i`) | S2 |
| Coverage | `--cov-fail-under=85` overall, plus a per-module report. The critical modules must be ≥ 95%: `agents/validators.py`, `ai/privacy.py`, `auth/permissions.py`, `documents/service.py` (`apply_metadata`), `ingest/submit.py` (dedupe), `vault/` (atomic write, render/rebuild), `agents/tools/facts.py` | S3 (S2 for the critical modules) |
| Mutation testing | `mutmut run` on the critical modules (nightly). Report the surviving mutants | below 80% killed → issue listing the surviving mutants |
| Requirement markers | `make qa-trace`: tests without `req` markers in feature areas, and requirement IDs without tests | S3 to the owner |
| Skips and xfails | every `skip`/`xfail` has `reason=` with an issue link or a milestone, and every xfail is `strict=True` | S3 |
| Flakiness | nightly reruns of failures ×3. A test that passes on rerun is **flaky**: issue labelled `flaky` with the trace. Fix it or quarantine it within 1 week. **CI never retries silently** | S3, or S2 if it hides an S1 area |
| Assertion quality | spot-review 10 random tests per milestone. Look for: asserting on mocks only, missing negative cases (permissions, privacy, invalid input), snapshot tests without meaning, sleeps instead of waits | review comments / S4 |
| Fakes match reality | the contract suite's `fake` and `real` parameters must both pass, and the drift test must be green | S2 to whoever owns the fake |
| Eval gates applied | PRs touching prompts, taxonomy or eval sets ran the eval gate, and baseline refreshes are justified in the PR | process issue to CL |
| `lessons-learned` | each milestone diff is checked against the "Never" list (a checklist in the audit report) | per item |

## 5.2 Defect workflow

**Severity:**

| Sev | Definition | Examples | Response |
|-----|------------|----------|----------|
| **S1** | data loss, privacy leak, security hole, wrong number or fabricated citation in an answer, a lost or overwritten user edit, a commit under a foreign identity | a restricted document in the proxy log; Alice sees Bob's document; an original deleted before verify; `apply_metadata` overwrites a manual field | **stop the line** in that area: merges there wait until it is fixed; fixed first; a regression test is mandatory; it is noted in the release report |
| **S2** | a core feature broken, or a contract violated | backfill duplicates; SSE buffered; setup check missing; an S1-class test failing | fixed in the current milestone of the owner |
| **S3** | degraded, or has a workaround | slow search; wrong empty state; misaligned control; flaky test | scheduled by the owner |
| **S4** | cosmetic | copy typo; a 1 px offset | batch |

**Issue content** (QAR-BUG-01):
- title `[S2][bug:cl] Gmail backfill imports the same attachment twice`
- environment (commit, stack profile)
- reproduction steps
- expected vs actual
- logs/trace/screenshot (no real data)
- the **failing test**: a path, ideally on a `qa/repro-<issue>` branch or committed as strict xfail referencing the issue
- the requirement IDs affected

**Lifecycle:** `new` → triaged (severity, area, owner) → `in progress` → fix PR (links the issue, includes the regression test) → QA re-verifies on `main` → `qa:verified` → closed. Reopen if the regression test turns flaky or fails again.

**Triage cadence:** new issues are triaged within one working session. A weekly snapshot goes into `docs/Developer-QA/bugs.md` (counts by severity and area, the oldest open S1/S2, trends).

## 5.3 Fix policy

QA is allowed to fix, but it must not become a third author silently rewriting the other tracks.

**QA fixes it directly** (a PR from `qa/fix-<issue>`) when **all** of these hold:
1. A failing test proves the bug, and it is committed in the same PR, before the fix in the commit order.
2. The fix is small: at most about 50 changed lines, in one module, with **no contract change** and no schema/migration change.
3. The owner has no open PR or in-progress milestone touching the same file (check open PRs and the owner's `STATUS.md`).
4. It doesn't change behaviour that a skill or plan defines differently. If the plan is wrong, raise that rather than coding around it.

Then:
- request the owner as the reviewer, and mention it in the issue
- the owner has 2 working days to object. With no response, QA may merge S1/S2 fixes once CI is green. S3/S4 fixes wait for the owner's approval.
- note the fix in the owner's area of `docs/Developer-QA/bugs.md` (QA does **not** edit the owner's `STATUS.md`; the owner updates it)

**Hand it to the owner** (issue + failing test only) when:
- the fix is bigger, touches several modules, or the cause is unclear
- it is a **contract mismatch** between OA and CL. QA writes the contract test that shows the mismatch and opens a `contract` issue tagged for both. The contract owners decide (working agreement §4). **QA never changes a contract alone.**
- it is a design or UX question (open it against the skill or plan, e.g. "the `document-chat` skill vs the actual Ask page")

**Never, even to unblock a release** (see the `lessons-learned` skill):
- weaken, delete or skip a failing test to make CI green (quarantine needs an issue and the owner's agreement, and is never allowed for S1-area tests)
- edit generated files by hand (regenerate them)
- commit under any identity but the repo owner's, or add co-author trailers
- use real personal data to reproduce a bug (build a synthetic reproduction)

## 5.4 Release gate (QA-M5)

**Before any `v*` tag:**
1. Freeze: a release candidate commit on `main`, with no merges except fixes for blockers.
2. Run, all on the candidate SHA:
   - the full nightly
   - `make qa-drills`
   - the upgrade test from the previous release
   - `make qa-trace --strict`
   - the manual checks MC-01…MC-09 (or a documented reason why one is not applicable)
3. Gate criteria = the [exit criteria](00-requirements.md#4-exit-criteria-for-v1-qa-sign-off): 100% traceability, contracts verified, E2E green twice in a row, non-functional green, test quality green, **zero open S1/S2**.
4. Write the report `docs/Developer-QA/reports/v1-acceptance.md` (later releases: `reports/release-<version>.md`):
   - SHA and environment
   - the matrix summary
   - journey results
   - non-functional results with numbers
   - drill results
   - the open S3/S4 list with owners
   - known limitations, in plain language
   - the decision: **GO** / **GO with known issues** / **NO-GO**
5. OA and CL acknowledge the report (a PR review). The repo owner tags the release. QA never tags.
6. After the release, a smoke run against the released images (GHCR) on a clean host confirms that the published artifacts work.

## 5.5 QA's own definition of done
- [ ] Tests carry requirement markers, are hermetic where they claim to be, and contain no real data.
- [ ] Strict xfails reference an issue or milestone.
- [ ] Every new suite runs in a Make target and a workflow, and is documented in `.github/workflows/README.md` (append-only touchpoint).
- [ ] [STATUS.md](STATUS.md) and the traceability matrix are updated.
- [ ] Any new general lesson is added to the [`lessons-learned`](../../.agents/skills/lessons-learned/SKILL.md) skill.

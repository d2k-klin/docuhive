# QA-01 — Strategy, traceability, system test harness (QA-M0, QA-M1)

## Paths QA owns

| Path | What |
|------|------|
| `docs/Developer-QA/` | these plans, `traceability.md`, `reports/`, `bugs.md` (triage log), `manual-checks.md` |
| `tests/system/` | Python system tests against the running stack (API level, worker, DB, vault) |
| `tests/e2e/` | Playwright full-stack user journeys (browser level) |
| `tests/corpus/` | synthetic document corpus generator + manifest (no real data) |
| `tests/mocks/` | mock Gmail API, mock Microsoft Graph, capturing LLM proxy, ntfy mock |
| `tests/perf/` (shared with OA's search bench) | load and latency benches |
| `services/docuhive/tests/contracts/` | **co-maintained**: QA keeps the suite complete and parametrised (real + fake). OA and CL add cases for their contracts |
| `deploy/compose.e2e.yml` | the full system-test stack |
| `.importlinter` | track boundary rules |
| `.github/workflows/system.yml`, `.github/workflows/nightly.yml` | main smoke, and the nightly full run |

Branches are named `qa/<topic>`. The [working agreement](../shared/working-agreement.md) rules apply: commits only under the owner's identity, and only append to shared touchpoints (`Makefile` targets `qa-*`, `pyproject.toml` dev deps, `package.json` dev deps).

---

## QA-M0 — Strategy, traceability, bug process

### Tasks
1. **Test pyramid, and who writes what:**

   | Layer | Written by | Runs | Tools |
   |-------|-----------|------|-------|
   | Unit (fakes, no network) | OA / CL | every PR | pytest, Vitest |
   | Contract (real + fake parametrised) | OA / CL add, QA completes | every PR | pytest |
   | Integration (one component + real deps) | OA / CL | `main` + labelled PRs | pytest + `compose.test.yml` |
   | System (whole backend running) | **QA** | `main` smoke + nightly | pytest + `compose.e2e.yml` |
   | E2E (browser journeys) | **QA** (OA/CL may add) | `main` smoke + nightly | Playwright + axe |
   | Non-functional (perf, security, a11y, visual, drills) | **QA** | nightly + release | k6/pytest-benchmark, ZAP, axe, Playwright screenshots |
   | Evals (AI quality) | CL; QA checks that the gates are applied | eval gate + nightly | `docuhive eval` |

2. **Traceability** — `docs/Developer-QA/traceability.md`:
   - Columns: requirement ID → tests (file::name) → type → status → last run → notes.
   - Generator `tests/system/tools/trace.py` (`make qa-trace`):
     1. Parse the requirement IDs from `docs/REQUIREMENTS.md` (regex `\*\*([A-Z]+-\d+)\*\*` plus the NFR table).
     2. Collect `@pytest.mark.req(...)` markers (pytest `--collect-only -q` plus a plugin) and the `@REQ-ID` tags in Playwright test titles.
     3. Merge in `manual-checks.md` entries.
     4. Write the table and print the uncovered IDs. It exits non-zero in release mode (`--strict`).
   - Register the `req` marker in the pytest config (append to `pyproject.toml`).
3. **Manual checks register** `docs/Developer-QA/manual-checks.md`: for things that can't be automated (a real WD NAS, a real iPhone camera, a real Gmail account, a calendar subscription). Each entry has an ID, steps, expected result, last run (date, environment, result), and the person who ran it.
4. **Bug process:**
   - issue templates (if the existing `.github/ISSUE_TEMPLATE/bug_report.yml` lacks severity and area fields, propose an additive change to the repo owner rather than editing it unilaterally)
   - labels: `S1`…`S4`, `bug:oa`, `bug:cl`, `bug:integration`, `flaky`, `qa:verified`
   - a triage log `docs/Developer-QA/bugs.md` (weekly snapshot)

   Details are in [05](05-test-audit-bugs-and-release.md).
5. **Seed the "test ahead" backlog:** write strict-xfail placeholders for the first contract tests (I2–I5) and journeys E2E-01…E2E-05, so the matrix shows coverage intent from day one.

### Acceptance
- `make qa-trace` produces the matrix, with every requirement ID listed (covered or not).
- The bug labels exist, and the triage log is started.

---

## QA-M1 — System test harness

**Goal:** one command brings up the whole product, seeded and fully observable, with **no external dependency** by default.

### 1.1 Stack — `deploy/compose.e2e.yml`
It extends OA's `compose.yml` (no copy: `include:` / `extends`), with test-specific overrides:

| Service | Purpose |
|---------|---------|
| `postgres`, `gotenberg`, `api`, `worker-ocr`, `worker`, `web`, `migrate` | the real product images built from this commit, `DOCUHIVE_ENV=test` |
| vault volume `e2e-vault` mounted at `/srv/vault` | stands in for the NAS. A `nas-toggle` sidecar can unmount it or rename `VAULT_ID` (the NAS-down drill) |
| `llm-proxy` (`tests/mocks/llm_proxy/`) | **capturing proxy**: every outbound AI request goes through it (provider base URLs point at it). It records `{provider, model, prompt_sha, body}` to a JSONL file and forwards to the fake backend or to Ollama. Used by the privacy tests (QAR-NF-01) |
| `fake-llm` (`tests/mocks/fake_llm/`) | an OpenAI-compatible and Anthropic-compatible HTTP server returning scripted answers keyed by prompt name + document marker, deterministic. It makes the system stack behave like CL's `FakeModel`, but over HTTP |
| `ollama` (profile `real-ai`) | the real local model for the nightly provider smoke (`qwen3:4b`, a small embedding model) |
| `mock-gmail`, `mock-graph` (`tests/mocks/mailapi/`) | FastAPI apps implementing exactly the Gmail and Graph endpoints CL's connectors use, served from fixture mailboxes (built from CL's recorded fixtures + the synthetic corpus), plus a fake OAuth token endpoint |
| `greenmail` | a real IMAP server (GreenMail, Apache-2.0), loaded with the synthetic mailbox |
| `mailpit` | SMTP sink for the email notification channel (MIT) |
| `ntfy-mock` | records ntfy POSTs |
| `zap` (profile `security`) | the OWASP ZAP baseline scan |

**Testability requests to CL and OA.** These are additive config. Open them as issues labelled `contract` (QA does not edit their code for this):
- `DOCUHIVE_MAIL_GMAIL_API_BASE`, `DOCUHIVE_MAIL_GRAPH_API_BASE`, `DOCUHIVE_MAIL_GOOGLE_TOKEN_URL`, `DOCUHIVE_MAIL_MS_AUTHORITY` overrides (allowed only with `ENV=test`)
- `providers.*.base_url` honoured for every provider kind (including Anthropic and Bedrock endpoint override), so traffic can go through `llm-proxy`
- a `DOCUHIVE_TEST_CLOCK` override (`ENV=test` only) for reminders and budget month-boundary tests

### 1.2 Synthetic corpus — `tests/corpus/`
- `generate.py`: seeded and reproducible. It writes about 150 documents plus `manifest.yaml`, holding the **ground truth** for each document: category, type, correspondent, date, facts, and whether it is restricted.
  - **Born-digital PDFs:** invoices (electricity, gas, internet), bank statements, payslips, contracts with notice periods, insurance policies with renewal dates, tax letters, receipts. Created with `reportlab` (BSD) from templates in German and English.
  - **Scans:** the same PDFs rasterised at 200 dpi, with noise, skew (±3°), shadows and 90° rotation (Pillow).
  - **Phone photos:** JPEG with an EXIF orientation tag (portrait stored sideways), perspective warp, and HEIC variants.
  - **Office files:** docx/xlsx made with `python-docx` and `openpyxl`.
  - **Email:** `.eml` with PDF attachments, HTML-only receipts, newsletters (should be rejected), inline logos (should be skipped), and duplicates of the same attachment across two mails.
  - **Hostile files:** these come from OA's malicious fixture set, referenced rather than copied.
  - **Restricted examples:** medical report, ID card, health insurance letter, plus one with the `private` tag.
  - **Multi-user:** a `user_b` subset of private documents for the isolation tests.
- All names, companies and IBANs are fake. IBANs are valid-checksum but in test ranges, and companies are invented (e.g. "Stadtwerke Musterstadt"). `tests/corpus/ALLOWLIST.md` lists the fake identifiers the hygiene scanner may see (QAR-NF-08).
- The mailboxes for the mocks and GreenMail are built from the same manifest, so every system test knows the expected outcome.

### 1.3 Seeding & helpers — `tests/system/conftest.py`
- `stack` fixture: waits for `/api/system/health`, runs `docuhive db upgrade`, creates users `alice` (admin) and `bob` (member) with API tokens, and runs `docuhive vault init`.
- Helpers:
  - `upload(path, as_user)`
  - `wait_for(doc_id, status, timeout)`, polling `GET /api/documents/{id}`
  - `wait_jobs_idle()`, polling `/api/system/jobs`
  - `run_drill(name)`
  - `llm_calls()`, which reads the proxy log
  - `db()`, a read-only SQL session for assertions
  - `vault_path(doc_id)`
- Reset between modules: drop and recreate the DB and vault volume (fast path: `TRUNCATE` all tables + wipe the vault, about 2 s). Each test module states which corpus subset it seeds.
- **Write-ownership guard:** a Postgres event trigger in the test DB logs every `INSERT/UPDATE/DELETE` with `application_name`. The API and worker set `application_name` to the module path of the writing code (requested from OA as a test-only setting). The test then asserts that CL code paths never wrote core tables directly (QAR-INT-03).

### 1.4 Playwright project — `tests/e2e/`
- `playwright.config.ts`:
  - projects `desktop-light` (1280×800), `desktop-dark`, `tablet` (768×1024) and `mobile` (375×812, touch)
  - `baseURL` = the e2e web service
  - traces and screenshots on failure, retries **0** (flakes must be visible)
- Fixtures: a logged-in page per user (storage state created via the API login), `@axe-core/playwright` for an `expectNoA11yViolations(page)` helper, and a `measureControls(page)` helper that returns every interactive control's bounding box (used by QAR-NF-05).
- Tags: `@smoke`, `@J1`…`@J5`, and requirement IDs.

### 1.5 Make targets (append to the `Makefile`)
| Target | Does |
|--------|------|
| `qa-up` / `qa-down` | the e2e stack up (built from the current tree) / down with volumes |
| `qa-system` | `pytest tests/system -m "not slow"` |
| `qa-e2e` | Playwright, all projects. `qa-e2e-smoke` runs `@smoke` only |
| `qa-nightly` | system + e2e + perf + security + visual + mutation + flake rerun |
| `qa-trace` | the traceability matrix |
| `qa-drills` | the resilience drills |
| `qa-corpus` | regenerate the synthetic corpus |

### 1.6 CI
- `.github/workflows/system.yml`:
  - Runs on push to `main`: build the images, `qa-up`, `qa-system` (smoke), `qa-e2e-smoke`, the boundary checks (import-linter, route ownership).
  - Uploads the Playwright report and the proxy log as artifacts.
  - `permissions: contents: read`, with actions pinned to a SHA.
- `.github/workflows/nightly.yml` (02:00 UTC, plus manual dispatch):
  - everything, including the `real-ai` profile with Ollama on the runner (CPU, small models)
  - ZAP
  - the perf benches, compared with the last baseline (`tests/perf/baselines.json`)
  - mutation testing on the critical modules
  - flake detection (rerun failed tests 3×, logging to the `flaky` issue)
  - a run report committed nowhere: it is posted as an artifact, and summarised into `docs/Developer-QA/reports/nightly-latest.md` only by a manual weekly PR

### Acceptance
- `make qa-up && make qa-system` passes on a clean machine with no internet beyond pulling the images. The proxy log shows only `fake-llm` traffic.
- The corpus generator is deterministic (same seed → same hashes) and contains no non-allow-listed identifiers.
- The smoke workflow runs green on `main` (initially with strict xfails where features are missing).

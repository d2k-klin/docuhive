# Developer OA — Status

Update this file whenever a milestone or a contract item changes state (working agreement §10).

| Milestone | State | Updated | Notes |
|-----------|-------|---------|-------|
| OA-M0 Repo skeleton + contract stubs + CI | in progress | 2026-11-03 | Workspaces, exact contract models, stubs, CLI, health, CI and contributor tooling implemented; local build/checks passing, CI publication unverified. |
| OA-M1 OCR spike + gate | in progress | 2026-11-04 | Spike, conversion/OCR, synthetic generator and CER tool implemented; current trixie worker passes real synthetic OCR. Private corpus and target-host measurements unavailable; gate pending. |
| OA-M2 Platform (settings, overlay, DB, jobs, worker) | complete | 2026-11-04 | Settings/overlay/plugins, schema/migrations and jobs/worker/scheduler implemented; PostgreSQL concurrency, scheduler leadership and killed-worker lease recovery verified. |
| OA-M3 Ingest pipeline, vault, documents service | not started | 2026-11-03 | |
| OA-M4 Auth, API, FTS + hybrid search | in progress | 2026-11-04 | Auth, scoped tokens, visibility, document/chunk FTS, typo fallback and hybrid fusion implemented. Real search checks pass. Document API and 20k-document latency acceptance remain pending. |
| OA-M5 Web shell + document UI | in progress | 2026-11-04 | Shell, login, BFF, generated types, knowledge-base management and token settings implemented and browser-tested. Archive workflows and setup wizard remain pending. |
| OA-M6 PWA capture + consume folder | not started | 2026-11-03 | |
| OA-M7 Ops: compose, NAS, backups, drills | not started | 2026-11-03 | |
| OA-M8 Hardening + cloud profile | not started | 2026-11-03 | |

## Contract items provided (CL swaps fallbacks for these)
- [x] I1 skeleton, `contracts/models.py`, stub modules (2026-11-03; local model/contract checks pass)
- [x] I2 `config.load_yaml/prompt/plugins`, `db.session`, intel Alembic env, `jobs.*` (real PostgreSQL evidence, including worker kill/recovery)
- [ ] I3 `documents.get/get_content/apply_metadata/iter_ids`, `document.*` events
- [ ] I4 `ingest.submit/incoming_dir`
- [ ] I5 `auth.current_user/visible_docs`, `documents.get_for_user`, `search.hybrid/register_semantic`
- [ ] I6 web shell, BFF proxy (SSE verified), generated API client, slot placeholders

## Current integrations
- I7 uses the public taxonomy loader and defaults.
- I8 supports both document and chunk semantic registration; FTS-only remains available.
- I9 the intelligence pages and exported slot components are present; complete archive screens still await OA-M3.
- I10 chunk retrieval and `ChunkHit` are implemented, including source ranks and document links.
- I11 saved knowledge-base table and `kb.get(user, kb_id)` are implemented and tested.

## Gate result (OA-M1)
- Decision: **pending** ([gate record](../decisions/0001-ocr-gate.md)). The user confirmed no private corpus or reference transcriptions are available. Do not infer GO or NO-GO from synthetic checks.

## Knowledge-base work (2026-11-04)

- KB-M1: shared rank fusion, chunk retrieval, source ranks, URLs, pre-cutoff chunk cap
  and typo fallback implemented. FTS still computes chunk vectors until I13 lands.
  Document search keeps a document FTS path so unembedded documents remain searchable.
- KB-M2: core revision `0002_knowledge_bases`, typed CRUD/status, owner-only changes,
  caller-visible counts, validated filters, suggestions and filter choices implemented.
- KB-M6 OA portion: `/knowledge` manager and `/settings/tokens` implemented. Tokens
  support `kb:read`/`kb:ask` and a session-issued `local_consumer` flag. CL's retrieval,
  answer and MCP APIs, test panel and Ask chip remain outside this work. Setup-wizard
  integration awaits the main OA-M5 setup flow.
- Learning: note/example 09 and the in-app explanation are available.

## Current verification

- Full offline suite: **330 passed, 49 integration tests deselected, 1 expected
  failure**, **86% coverage**. The later focused run for the final suggestion
  validation and documentation/example checks also passes (**14 tests**).
- Complete OA integration suite: **32 passed** on the disposable PostgreSQL and
  Gotenberg stack. This includes the new migration, CRUD permissions, shared-base
  visibility, counts, pagination, stemming, typo retrieval, long-document
  diversification, worker kill/lease recovery, queue concurrency and conversion.
- Web logic: **6 passed**. Full real-API browser suite: **24 passed**, at 375/768/1280
  in light and dark, including axe, no-overflow checks, controls, sign-in/out,
  saved-scope create/edit/delete and token create/revoke. Screenshots were inspected.
- Global mypy: **105 source files passed**; Ruff and web ESLint passed. The normal
  Next.js production build (Turbopack) passes in the isolated web workspace with
  its own dependency copy and complete standalone tracing. Compiler IPC required
  local-port permission and clearing the earlier failed build cache. The active
  development server was left running.
- Import-linter keeps the OA boundary and shared-model leaf contracts. Its CL
  boundary fails on private `config.settings` imports in `ai/cli.py`, `mail/oauth.py`,
  `notify/__init__.py` and `notify/jobs.py`. These CL-owned files were not changed.
- The docs link check now excludes ignored temporary/private trees, so QA preview
  artifacts cannot fail the public-repository check. All public links pass.
- Current trixie worker image builds from the source archive and passes real OCR
  as UID 1000 with a read-only root and network disabled: `pdfa=True`, PDF/A part 2,
  all expected German test words present. This is **not** real-corpus gate evidence.
- Ghostscript 10.5.1 warns about multi-character ToUnicode mappings in complex
  scripts. The German smoke passes; broader script fidelity remains unverified.
- macOS `make` is currently blocked by the machine's unaccepted Xcode licence;
  the exact Docker build/run steps from `ocr-smoke` were run directly.

## Next dependency

The selected archive implementation (OA-M3), document workflows and deployment
acceptance remain dependent on the measured OA-M1 backend decision.

## Architecture documentation (2026-11-04)

- Added the handwritten architecture illustration to [the architecture guide](../ARCHITECTURE.md).
  The separate clean system map is used by the Mr.D technical article; both mark incomplete
  archive work and the in-progress KB management API/UI, with retrieve/Ask HTTP APIs and MCP
  still planned.
- Source review corrected API-streamed chat, separate embedding clients, database recovery
  scope, the mail-token key and the limits of the privacy audit constraint.
- Documentation link test: **1 passed** on a clean mirror of public repository files. The
  working-copy run finds four broken links in ignored `tmp/qa/readme-preview` artifacts.
- Mr.D source and generated article/assets updated locally; build and static checks pass
  (**64 pages, 187 files**). No commit, push, deployment or live-provider/hardware acceptance
  is claimed by this documentation work.

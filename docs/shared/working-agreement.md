# DocuHive — Working agreement (OA + CL)

These rules let two developers work in one repo **at different speeds, without waiting on each other**.

## 1. Golden rules

1. **Never block.** If something you need from the other track is not done, use the fallback from [README.md § Integration points](README.md#integration-points), keep going, and note the swap-in as a TODO in your `STATUS.md`.
2. **Only edit files you own.** Ownership is in [contracts.md §5–7](contracts.md) and the `CODEOWNERS` file. The one exception is the shared touchpoints (§3), which are append-only.
3. **Contracts are the only coupling.** Do not import the other track's private modules. Read-only SQL on the other track's tables is allowed (contracts §5).
4. **Main is always green and runnable.** Unfinished features hide behind config. If something is not configured, it is off (e.g. no AI provider configured → classification jobs wait as "no handler"/"disabled", nothing crashes).
5. **Keep `STATUS.md` current.** Update it whenever a milestone or a contract item changes state. It is how the other developer learns what is ready.

## 2. Bootstrapping (whoever starts first)

OA owns the skeleton (OA-M0). If CL is ready to work in the repo before OA-M0 is merged, CL may create the **minimum** skeleton itself:
- `services/docuhive/pyproject.toml`
- `src/docuhive/contracts/models.py`, verbatim from contracts §1
- the stub modules from contracts §2, with exact signatures, raising `NotImplementedError`

The PR must be titled `bootstrap: skeleton per contracts v1`. OA later extends it rather than replacing it. Before that, CL can work in `spikes/cl/`, which needs no repo structure.

## 3. Shared touchpoints (append-only, no review wait)

Both developers may **append** to these files without waiting for review. Never reorder or remove the other's lines.

| File | What you may add |
|------|------------------|
| `services/docuhive/pyproject.toml` | dependencies (CL: put AI/mail deps in the `[project.optional-dependencies] ai` and `mail` extras) |
| `uv.lock`, `apps/web/package-lock.json` | regenerate after rebasing (`uv lock`, `npm install`). Never hand-merge |
| `docuhive/api/routers.py` → `ROUTERS` | your router import + entry |
| `docuhive/worker/handlers.py` → `HANDLER_MODULES` | your handler module path |
| `apps/web/lib/nav.ts` | your nav entries |
| `apps/web/lib/api/openapi.json`, `schema.d.ts` | regenerate (`make gen-api`) |
| `.env.example` | variables in your prefix section |
| `AGENTS.md` | a section for your area (OA owns the rest) |
| `deploy/compose.yml` | nothing. CL adds services in `deploy/compose.ai.yml` (CL-owned) |
| `.github/workflows/` | your own workflow files (OA: `ci.yml`; CL: `evals.yml`) |

## 4. Changing a contract

- **Additive changes** (a new optional field, a new function, a new event kind, a new route prefix) are allowed:
  1. Update `docs/shared/contracts.md` and `contracts/models.py` in the same PR.
  2. Bump nothing.
  3. Tag the PR `contract`.
  4. Merge after CI is green. The other developer reviews it afterwards, asynchronously.
- **Breaking changes** (rename, removed field, changed semantics) need the other developer's **explicit approval** on the PR:
  1. Bump `CONTRACT_VERSION`.
  2. Keep the old form working for one milestone (deprecation shim) where feasible.
- **Disagreements**: the owner of the function decides on the *implementation*; both must agree on the *contract*. If there is no response after 3 days, an additive change stands, and a breaking change waits.

## 5. Git & PRs

- Trunk-based. Short branches: `oa/<topic>` and `cl/<topic>`. Rebase on `main` before merging. Squash-merge.
- PR template: what, which requirement IDs, which milestone task, tests, `STATUS.md` updated (y/n).
- **Review**: changes inside your own area are self-merged once CI is green. The other developer is requested as a reviewer only for contract changes, `CODEOWNERS`-protected shared files, or anything security-sensitive (auth, privacy gate, secrets).
- Commit messages are in the imperative mood ("Add vault atomic writer").
- **One identity:** every commit, from OA, CL or any coding agent, is authored and committed by the repo owner's git identity (`d2k-klin`). No other author or committer, no `--author` or env overrides, no `Co-authored-by:` trailers. Check with `git log --format='%an <%ae> | %cn <%ce>'` before pushing.
- Never commit: `overlay/`, `.env`, real documents, OAuth tokens, eval reports built from private data.

### CODEOWNERS (OA creates it in OA-M0; fill in GitHub handles)
```
*                                   <oa-handle>
/docs/Developer-CL/                 <cl-handle>
/services/docuhive/src/docuhive/ai/        <cl-handle>
/services/docuhive/src/docuhive/agents/    <cl-handle>
/services/docuhive/src/docuhive/mail/      <cl-handle>
/services/docuhive/src/docuhive/taxonomy/  <cl-handle>
/services/docuhive/src/docuhive/review/    <cl-handle>
/services/docuhive/src/docuhive/index/     <cl-handle>
/services/docuhive/src/docuhive/chat/      <cl-handle>
/services/docuhive/src/docuhive/reminders/ <cl-handle>
/services/docuhive/src/docuhive/notify/    <cl-handle>
/services/docuhive/migrations/intel/       <cl-handle>
/services/docuhive/tests/intel/            <cl-handle>
/evals/                             <cl-handle>
/config/defaults/taxonomy.yaml      <cl-handle>
/config/defaults/routing.yaml       <cl-handle>
/config/defaults/mail-rules.yaml    <cl-handle>
/config/defaults/prompts/           <cl-handle>
/apps/web/components/intel/         <cl-handle>
/apps/web/app/(app)/review/         <cl-handle>
/apps/web/app/(app)/ask/            <cl-handle>
/apps/web/app/(app)/analyses/       <cl-handle>
/apps/web/app/(app)/sources/        <cl-handle>
/apps/web/app/(app)/reminders/      <cl-handle>
/apps/web/app/(app)/settings/ai/    <cl-handle>
/apps/web/app/(app)/settings/notifications/ <cl-handle>
/deploy/compose.ai.yml              <cl-handle>
/.github/workflows/evals.yml        <cl-handle>
/docs/shared/                       <oa-handle> <cl-handle>
/services/docuhive/src/docuhive/contracts/ <oa-handle> <cl-handle>
```

## 6. Python package layout & ownership

```
services/docuhive/src/docuhive/
├─ contracts/      JOINT    models.py (contracts §1)
├─ config/         OA       settings, overlay loader, plugins
├─ db/             OA       engine, session, CoreBase, IntelBase
├─ jobs/           OA       queue, handlers registry, periodic
├─ worker/         OA       loop, handlers.py (touchpoint)
├─ ingest/         OA       pipeline, convert, ocr, text, thumbs, consume poller
├─ vault/          OA       layout, atomic writes, meta.json, rebuild, library view
├─ documents/      OA       service (contracts §2.5), vocabulary
├─ auth/           OA       users, sessions, tokens, permissions
├─ search/         OA       fts, hybrid, register_semantic
├─ api/            OA       app factory, routers.py (touchpoint), core routers
├─ cli.py          OA       `docuhive` entrypoint (CL adds subcommands via `docuhive.ai.cli:register`)
├─ ai/             CL       settings, router, providers, privacy, budgets, embeddings, startup, cli
├─ agents/         CL       base (harness), triage, classify, extract, ask, tools/
├─ taxonomy/       CL       schema validation, loader
├─ review/         CL       review_items, API
├─ mail/           CL       settings, oauth, gmail, graph, imap, prefilter, sync, backfill, API
├─ index/          CL       chunking, doc_chunks, semantic search
├─ chat/           CL       sessions, SSE, analyses
├─ reminders/      CL
└─ notify/         CL
migrations/core/   OA
migrations/intel/  CL       (env scaffold created by OA in OA-M2)
tests/core/        OA
tests/intel/       CL
tests/fakes/core.py   fakes of OA contracts (written by whoever needs them first; OA maintains)
tests/fakes/intel.py  FakeLLM, fake taxonomy, fake semantic fn (CL maintains)
```

## 7. Database migrations

- OA writes migrations in `migrations/core`, CL in `migrations/intel`. Separate version tables mean there are **no merge-head conflicts** between the tracks.
- Generate migrations with autogenerate against **your own** metadata only (`CoreBase.metadata` or `IntelBase.metadata`). Each env's `env.py` already restricts this.
- Never edit a merged migration; add a new one instead.
- `docuhive db upgrade` runs core → intel. `docuhive db downgrade` is for dev only.

## 8. Testing

- `pytest -m "not integration"` is fast, needs no Docker and runs on every PR.
- `pytest -m integration` uses `deploy/compose.test.yml` (Postgres, Gotenberg, the worker image). It runs in CI on `main` and on PRs labelled `integration`.
- Each contract has a **contract test** in `tests/contracts/` (jointly owned). It runs the same assertions against the fake and against the real implementation, so a fake cannot drift from reality.
- No real documents or real mail in the repo. Test fixtures are synthetic (`tests/fixtures/`, `evals/synthetic/`).

## 9. Definition of done (every task)

- [ ] The code is in your owned paths, and touchpoints are only appended to.
- [ ] Unit tests for non-trivial logic; contract tests updated if a contract was touched.
- [ ] `make lint test` is green locally, and CI is green.
- [ ] Config documented in `.env.example` / `config/defaults/*` with comments.
- [ ] User-facing behaviour reflected in `docs/` (setup or usage) where relevant.
- [ ] `STATUS.md` updated (task ticked, contract items marked).

## 10. STATUS.md format

```markdown
| Milestone | State | Updated | Notes |
|-----------|-------|---------|-------|
| OA-M3 Ingest + vault | in progress | 2026-12-02 | OCR done, quarantine pending |

## Contract items provided
- [x] I2 jobs.enqueue/handler/periodic (2026-11-20)
- [ ] I3 documents.apply_metadata

## Using fallbacks for
- I7 taxonomy.load (fixture) — swap in when CL marks done
```
States: `not started` · `in progress` · `done` · `blocked (reason)`. "Blocked" should be rare; prefer a fallback.

## 11. Communication

- Asynchronous by default: GitHub issues with the labels `contract`, `question:oa`, `question:cl`, `bug:oa`, `bug:cl`.
- A bug in the other track: open an issue with a failing test if possible. Don't fix it in their code, unless it is a one-line fix and you tag them.
- Weekly (or whenever) a 15-minute sync is optional. `STATUS.md` replaces status meetings.

## 12. Tooling (OA sets it up in OA-M0)

A root `Makefile`, the same convention as the sibling d2k-klin repos (ReelHive, SentryHive). The target list is in the [`repo-structure` skill](../../.agents/skills/repo-structure/SKILL.md#makefile-targets-keep-these-names):
- `make setup`, `make dev`, `make test`, `make test-ui`, `make test-integration`, `make lint`, `make fmt`
- `make db-upgrade`, `make gen-api`, `make eval` / `make eval-baseline` (CL), `make spike-ocr DIR=…` (OA), `make learn`

Tools:
- Python: `uv`, ruff (lint + format), mypy, pytest (coverage gate 85%)
- Web: eslint, `tsc --noEmit`, prettier, Vitest, Playwright + axe
- Pre-commit: ruff, prettier, gitleaks

## 13. Project skills (both developers and their coding agents)

The skills in [`.agents/skills/`](../../.agents/skills/README.md) are binding conventions, not suggestions. Load the matching skill before starting a task:

| Skill | OA | CL |
|-------|----|----|
| `repo-structure` | every new file/folder, OA-M0 | every new file/folder |
| `docuhive-ui` | all OA pages, the tokens, `/dev/ui` | all CL pages and slot components |
| `guided-experience` | the `/setup` wizard, dashboard checklist, system setup checks, error copy | AI/mail/notification setup checks, step content, error codes |
| `document-pipeline` | ingest, vault, consume, upload | email sources, AI pipeline jobs |
| `document-editing` | the detail page, bulk edit, locks/undo | review queue edit controls, `DocumentAIPanel` |
| `document-chat` | the ⌘K palette and "Ask about these" entry points | the Ask page, agent, tools |
| `lessons-learned` | before every milestone and PR review | before every milestone and PR review |
| `strands-agent-harness` | — | every model call |
| `learning-showcase` | notes 09 (hybrid search), 12 (pipelines) | notes 01–08, 10, 11; examples; "How was this made?" |

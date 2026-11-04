# OA-01 — Foundations (OA-M0, OA-M2)

## OA-M0 — Repo skeleton, contract stubs, CI

**Goal:** a repo both developers can work in on day one. **Size:** 1–3 days. **Unblocks:** I1.

### Tasks
1. **Root files**
   - `LICENSE` (Apache-2.0, pending Q5 in the requirements)
   - `README.md` (keep the doc links)
   - `.gitignore`: `overlay/`, `.env*` except `.env.example`, `*.local.*`, `data/`, `tmp/`, `evals/reports/`, `node_modules/`, `.venv/`, `__pycache__/`, `.next/`
   - `.env.example`, with sections per prefix (contracts §8)
   - `CODEOWNERS` (working agreement §5)
   - `AGENTS.md` (see below) and `CLAUDE.md` (one line: "See AGENTS.md")
   - `Makefile` (working agreement §12, targets from the `repo-structure` skill)
   - `.pre-commit-config.yaml` (ruff, prettier, gitleaks)
2. **Python package** `services/docuhive/`:
   - `pyproject.toml`: Python 3.12, built with hatchling. Deps: `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pydantic-settings`, `sqlalchemy>=2`, `alembic`, `psycopg[binary]`, `pgvector`, `httpx`, `pyyaml`, `python-ulid`, `argon2-cffi`, `cryptography`. Extras `ai` and `mail` are left empty for CL. Dev group: `pytest`, `pytest-asyncio`, `ruff`.
   - `src/docuhive/contracts/models.py`, **verbatim** from contracts §1, plus `contracts/__init__.py` re-exporting everything.
   - **Stub modules** with the exact contract signatures from contracts §2, raising `NotImplementedError("OA-Mx")` and naming the milestone that implements them:
     - `config/__init__.py`, `db/__init__.py`, `jobs/__init__.py`, `ingest/__init__.py`
     - `documents/__init__.py`, `auth/__init__.py`, `search/__init__.py`
   - `api/app.py`: a `create_app()` factory, `GET /api/system/health → {"status":"ok","version":…}`, and the `api/routers.py` touchpoint containing `ROUTERS: list[APIRouter] = [system_router]`.
   - `worker/handlers.py`: the touchpoint `HANDLER_MODULES: list[str] = []`.
   - `cli.py`: an `argparse` CLI named `docuhive` with subcommands `api`, `worker`, `db`, `openapi` (stubs where not yet implemented), plus a hook that calls `docuhive.ai.cli.register(subparsers)` if it is importable.
   - Test folders `tests/core/`, `tests/intel/` (empty with `.gitkeep`), `tests/contracts/test_models.py` (models import and round-trip JSON), and `tests/fakes/core.py` with an empty module docstring.
3. **Web app** `apps/web/`:
   - `create-next-app` with TypeScript, App Router, Tailwind and ESLint.
   - Strict `tsconfig`, and a blank `app/page.tsx` that says "DocuHive".
   - Scripts: `dev`, `build`, `lint`, `typecheck`, `gen:api`. The `gen:api` script runs `openapi-typescript lib/api/openapi.json -o lib/api/schema.d.ts`.
4. **Dev compose** `deploy/compose.dev.yml`:
   - `postgres` (`pgvector/pgvector:pg16`, with the `unaccent`, `pg_trgm` and `vector` extensions created by an init script)
   - `gotenberg` (`gotenberg/gotenberg:8`)
   - Ports bound to `127.0.0.1` only.
5. **CI** `.github/workflows/ci.yml`:
   - Python: `uv sync`, `ruff check`, `ruff format --check`, `pytest -m "not integration"`
   - Web: `npm ci`, `lint`, `typecheck`, `build`
   - `gitleaks`
   - A licence check: `pip-licenses --fail-on "GNU Affero General Public License v3 (AGPLv3);AGPL"`, and `license-checker --failOn AGPL` for npm
6. **Docs:** `docs/decisions/` folder with `0000-template.md`.
7. **Status files:** create `docs/Developer-OA/STATUS.md` (already present, so just update it) and mark **I1 done**.
8. **Public-repo conventions** (load the [`repo-structure` skill](../../.agents/skills/repo-structure/SKILL.md); copy the house style from ReelHive):
   - `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` (private advisory link, design guarantees: local-first, privacy gate, no secrets in logs)
   - `CHANGELOG.md` with `[Unreleased]`
   - `.github/`: `CODEOWNERS`, `PULL_REQUEST_TEMPLATE.md`, `ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml`, `dependabot.yml` (pip, npm, github-actions), `copilot-instructions.md` (→ `AGENTS.md`), `workflows/README.md`. Actions are pinned to a SHA, with `permissions: contents: read`.
   - A `README.md` in every folder (the Overview / What's here / Extending format), and `docs/README.md` as the docs index (Using / Understanding / Learning / Extending / Planning).
   - `tests/unit/test_docs.py`: fails on broken relative links and anchors in any `*.md`.
   - `.agents/skills/` and `.claude/skills/` already exist. Keep them, and extend the root `AGENTS.md` (it already lists the skills).

### `AGENTS.md` content (OA writes; CL appends its section)
- The repo map (working agreement §6), and how to run: `make dev`, `make test`, `make lint`.
- Rules:
  - contracts first (`docs/shared/contracts.md`)
  - edit only owned paths
  - no AGPL imports
  - no real data in the repo
  - every non-trivial function gets a test
- Code style:
  - ruff defaults, line length 100, type hints everywhere, Pydantic for I/O models
  - TS strict, server components by default

### Acceptance
- A fresh clone, then `make dev` → Postgres and Gotenberg are up. `uv run docuhive --help` lists the subcommands. `curl localhost:8000/api/system/health` returns ok.
- `from docuhive.contracts import DocumentView, MetadataPatch` works.
- CI is green on `main`. A PR that adds an AGPL dependency fails CI (verify once with a throwaway branch).

---

## OA-M2 — Platform: settings, overlay, DB, jobs, worker, CLI

**Goal:** the runtime every feature sits on. **Unblocks:** I2.

### 2.1 Settings — `docuhive/config/settings.py`
A `pydantic-settings` `CoreSettings` with env prefix `DOCUHIVE_`:

| Var | Default | Notes |
|-----|---------|-------|
| `ENV` | `dev` | `dev` / `prod` / `test` |
| `DATABASE_URL` | `postgresql+psycopg://docuhive:docuhive@localhost:5432/docuhive` | |
| `VAULT_DIR` | `./data/vault` | the NAS mount in prod |
| `STAGING_DIR` | `./data/staging` | **must be local SSD**, never the NAS |
| `OVERLAY_DIR` | unset | path to the private overlay |
| `SECRET_KEY` | required in prod | 32+ bytes. Used for session signing and as the HKDF base |
| `AUTH_DISABLED` | `false` | allowed only with `ENV=dev` |
| `MAX_UPLOAD_MB` | `100` | |
| `OCR_LANGUAGES` | `deu+eng` | Tesseract language string |
| `OCR_JOBS` | `2` | parallel OCR pages per document |
| `PUBLIC_URL` | `http://localhost:3000` | for links and OAuth redirects (CL uses it) |

`get_settings()` is cached. The API and worker fail fast on invalid settings with a clear message.

### 2.2 Overlay + plugins — `docuhive/config/__init__.py`
- `load_yaml(name)`: read `config/defaults/<name>` (located via `importlib.resources` or a repo-relative path setting) and `$OVERLAY_DIR/<name>`, then deep-merge them. **Mappings merge recursively; lists and scalars from the overlay replace the default.** Results are cached, and `reload()` clears the cache.
- `prompt(name)`: read `prompts/<name>.md` from the overlay, falling back to the defaults. Parse the front-matter `version` (default `1`) and return `(body, f"{name}@{version}")`.
- `overlay_path(*parts)`: returns the path inside the overlay if it exists, otherwise `None`.
- `plugins(hook)`: iterate `importlib.metadata.entry_points(group="docuhive.plugins")`, load each one, and return `getattr(obj, hook)` where present. Errors are logged and skipped (a broken plugin must not crash the app).
- Tests:
  - the merge rules (nested dict merge, list replace, scalar replace, missing files)
  - prompt override and version parsing
  - a plugin that raises on load is skipped

### 2.3 Database — `docuhive/db/`
- `engine` from settings, and `session()` as a context manager (commit on success, rollback on error).
- `CoreBase` and `IntelBase`: two `DeclarativeBase` classes with **separate** `MetaData` objects.
- **Alembic:**
  - Two environments: `migrations/core` (`version_table="alembic_version_core"`, `target_metadata=CoreBase.metadata`) and `migrations/intel` (`version_table="alembic_version_intel"`, `target_metadata=IntelBase.metadata`).
  - Create the intel env scaffold with an **empty** initial revision, so CL only adds revisions.
  - `include_object` in each `env.py` excludes the other metadata's tables from autogenerate.
- **Core migration `0001_core`:**
  - extensions: `unaccent`, `pg_trgm`, `vector`
  - text search configurations (below)
  - tables: `users`, `sessions`, `api_tokens`, `correspondents`, `tags`, `documents`, `document_tags`, `doc_facts`, `doc_sources`, `notes`, `audit_log`, `jobs`, `settings`
  - The schemas that CL reads are in contracts §5.1. The remaining tables:

```sql
CREATE TABLE sessions (
  token_hash text PRIMARY KEY, user_id bigint NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL DEFAULT now(), user_agent text, ip inet);
CREATE TABLE api_tokens (
  id bigserial PRIMARY KEY, user_id bigint NOT NULL REFERENCES users(id), name text NOT NULL,
  token_hash text UNIQUE NOT NULL, prefix text NOT NULL, scopes text[] NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), last_used_at timestamptz, revoked_at timestamptz);
CREATE TABLE notes (
  id bigserial PRIMARY KEY, document_id text NOT NULL REFERENCES documents(id),
  user_id bigint NOT NULL REFERENCES users(id), body text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE audit_log (
  id bigserial PRIMARY KEY, at timestamptz NOT NULL DEFAULT now(), actor text NOT NULL,
  document_id text, action text NOT NULL, before jsonb, after jsonb);
CREATE TABLE jobs (
  id bigserial PRIMARY KEY, kind text NOT NULL, queue text NOT NULL DEFAULT 'default',
  payload jsonb NOT NULL DEFAULT '{}', status text NOT NULL DEFAULT 'pending',
    -- pending | running | done | dead
  attempts int NOT NULL DEFAULT 0, max_attempts int NOT NULL DEFAULT 5,
  run_after timestamptz NOT NULL DEFAULT now(), locked_at timestamptz, locked_by text,
  dedupe_key text, last_error text, note text,
  created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz);
CREATE INDEX jobs_pick ON jobs (queue, run_after) WHERE status = 'pending';
CREATE UNIQUE INDEX jobs_dedupe ON jobs (dedupe_key) WHERE status IN ('pending','running');
CREATE TABLE settings (key text PRIMARY KEY, value jsonb NOT NULL);
-- indexes
CREATE INDEX documents_tsv ON documents USING gin (content_tsv);
CREATE INDEX documents_title_trgm ON documents USING gin (title gin_trgm_ops);
CREATE INDEX correspondents_trgm ON correspondents USING gin (name gin_trgm_ops);
CREATE INDEX documents_owner ON documents (owner_id, deleted_at);
CREATE INDEX documents_date ON documents (document_date);
CREATE INDEX doc_facts_field ON doc_facts (field, value_date);
```

**Text search configurations** (unaccent for indexing *and* querying):
```sql
CREATE TEXT SEARCH CONFIGURATION dh_simple  (COPY = simple);
CREATE TEXT SEARCH CONFIGURATION dh_german  (COPY = german);
CREATE TEXT SEARCH CONFIGURATION dh_english (COPY = english);
ALTER TEXT SEARCH CONFIGURATION dh_simple  ALTER MAPPING FOR hword, hword_part, word WITH unaccent, simple;
ALTER TEXT SEARCH CONFIGURATION dh_german  ALTER MAPPING FOR hword, hword_part, word WITH unaccent, german_stem;
ALTER TEXT SEARCH CONFIGURATION dh_english ALTER MAPPING FOR hword, hword_part, word WITH unaccent, english_stem;
```
Add more languages later with one migration each (Q4 in the requirements). The language → config map lives in `search/fts.py`: `{"de": "dh_german", "en": "dh_english"}`, with `dh_simple` as the fallback.

### 2.4 Job queue — `docuhive/jobs/`
Implements contracts §2.3.
- **`enqueue`**: `INSERT … ON CONFLICT (dedupe_key) WHERE status IN ('pending','running') DO NOTHING RETURNING id`. If nothing is returned, select the existing id.
- **Pick**: in one transaction, run
  ```sql
  SELECT … FROM jobs WHERE status='pending' AND queue = ANY(:queues) AND run_after <= now()
  ORDER BY run_after LIMIT 1 FOR UPDATE SKIP LOCKED
  ```
  then set `status='running', locked_at=now(), locked_by=<host:pid:thread>, attempts=attempts+1`.
- **Run**: look up the handler by `kind`.
  - **No handler**: set `status='pending', run_after=now()+1h, attempts=attempts-1, note='no handler'`.
  - **Success**: `done`, and set `finished_at`.
  - **`RetryLater` or any exception**: if `attempts < max_attempts`, go back to `pending` with `run_after = now() + min(30s·2^(attempts-1), 1h)` and set `last_error`. Otherwise `dead`.
  - **`PermanentFailure`**: `dead` immediately.
  - **`ctx.defer(until)`**: `pending`, `run_after=until`, `attempts=attempts-1`.
- **Lease**: a job is `running` with `locked_at < now() - timeout_s`, and no heartbeat, means the worker died. The reaper (runs every minute) returns it to `pending`. `ctx.heartbeat()` updates `locked_at`.
- **Periodic**: the scheduler thread in the worker. For each `@periodic`, it enqueues with `dedupe_key=f"periodic:{kind}"` and tracks the last run in `settings['periodic:<kind>']`. Only one worker process runs the scheduler, guarded by a Postgres advisory lock `pg_try_advisory_lock(hashtext('docuhive-scheduler'))`.
- **Concurrency**: `docuhive worker --queues ocr --concurrency 1` and `docuhive worker --queues ai,mail,default --concurrency 4` (threads). Graceful shutdown on SIGTERM: stop picking jobs, finish the running ones (up to 30 s), and leave the rest to the reaper.
- **Cleanup**: a periodic `jobs.cleanup` (daily) deletes `done` jobs older than 30 days. `dead` jobs are kept.
- Import every module in `HANDLER_MODULES` at worker start, and call `docuhive.ai.startup()` if it is importable.
- **Tests:**
  - dedupe
  - retry/backoff timing
  - dead after max attempts
  - no-handler behaviour
  - defer
  - the reaper
  - two workers never pick the same job (two threads against a real DB, integration)
  - the scheduler advisory lock

### 2.5 Fakes for CL — `tests/fakes/core.py`
OA maintains this file (CL may write the first version, per the working agreement):
- `FakeJobs`: `enqueue` runs handlers synchronously (or collects jobs for assertions).
- `FakeDocuments`: an in-memory `DocumentView` store implementing `get`, `get_content`, `apply_metadata` (with the same manual-field semantics) and `iter_ids`.
- `FakeIngest`: `submit` copies files to `tmp/fake-vault/<ulid>/` and returns `IngestResult`, with sha256 dedupe.
- A pytest fixture `fake_core` that monkeypatches the contract modules.
- **Contract tests** in `tests/contracts/` run against the fakes now, and against the real implementations once they exist (parametrised fixture).

### 2.6 CLI
- `docuhive db upgrade|downgrade|current`: runs core, then intel.
- `docuhive api [--host --port --reload]`
- `docuhive worker --queues … --concurrency N`
- `docuhive user create <username> [--admin]` (prompts for the password; argon2)
- `docuhive openapi`: prints the schema (used by `make gen-api`)

### 2.7 System endpoints (admin)
- `GET /api/system/jobs?status=&kind=&queue=`: a cursor-paginated list.
- `POST /api/system/jobs/{id}/retry`: dead → pending.
- `GET /api/system/sse-test`: emits `tick` events every 500 ms, ten times. Used to verify SSE through the proxy in OA-M5.

### Acceptance
- `docuhive db upgrade` on an empty DB creates all core tables and the TS configs, and stamps the intel env.
- A demo handler registered in a test module processes jobs. Killing the worker mid-job leads to the job being retried after the lease expires.
- Overlay tests pass. Setting `DOCUHIVE_OVERLAY_DIR` to a temp dir with a `routing.yaml` changes the result of `load_yaml("routing.yaml")`.
- **I2 marked done** in `STATUS.md`.

# DocuHive — Contracts between OA and CL

Status: contract version **1** · binding for both tracks.
Change process: [working-agreement.md §4](working-agreement.md#4-changing-a-contract).

These are the **only** ways code from one track may use code or data from the other. Anything not
listed here is private to its owner and may change without notice.

---

## 1. Shared Python models — `docuhive/contracts/models.py`

Jointly owned. Whoever starts in the repo first creates this file **verbatim** (see the working agreement §2).

```python
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

CONTRACT_VERSION = 1

FactType = Literal["money", "date", "string", "number", "iban"]


class SourceKind(StrEnum):
    upload = "upload"      # web UI upload
    mobile = "mobile"      # PWA capture
    email = "email"        # CL mail connectors
    consume = "consume"    # scanner drop folder
    api = "api"            # personal API token (scripts, iOS Shortcuts)


class SourceInfo(BaseModel):
    kind: SourceKind
    original_filename: str
    account_id: int | None = None        # mail_accounts.id (CL table), email only
    message_id: str | None = None        # provider message id, email only
    email_from: str | None = None
    subject: str | None = None
    received_at: datetime | None = None


class DocStatus(StrEnum):
    staged = "staged"            # accepted, waiting for processing
    processing = "processing"    # convert / OCR running
    stored = "stored"            # in the vault, searchable
    quarantined = "quarantined"  # failed; input kept, retry possible


class FactValue(BaseModel):
    type: FactType
    value: str                   # canonical string: money "84.20", date "2026-11-20", number "12.5"
    currency: str | None = None  # ISO 4217, money only
    confidence: float | None = Field(default=None, ge=0, le=1)


class DocumentView(BaseModel):
    id: str                      # ULID
    owner_id: int
    shared: bool
    status: DocStatus
    mime: str                    # mime of the original
    pages: int | None
    added_at: datetime
    title: str | None
    document_date: date | None
    language: str | None         # ISO 639-1, e.g. "de"
    category: str | None         # taxonomy category id, e.g. "utilities/electricity"
    document_type: str | None    # taxonomy document type id, e.g. "invoice"
    correspondent: str | None    # display name
    tags: list[str]
    facts: dict[str, FactValue]
    manual_fields: list[str]     # fields a user set; AI must not overwrite
    source: SourceInfo
    deleted_at: datetime | None


class MetadataPatch(BaseModel):
    """None = leave unchanged. Facts merge per key; a fact set to None is removed."""
    title: str | None = None
    document_date: date | None = None
    language: str | None = None
    category: str | None = None
    document_type: str | None = None
    correspondent: str | None = None     # find-or-create by normalised name
    tags_add: list[str] = []
    tags_remove: list[str] = []
    facts: dict[str, FactValue | None] | None = None
    unlock_fields: list[str] = []        # user only: remove from manual_fields ("let AI manage again")


class Provenance(BaseModel):
    task: str                   # "classify" | "extract" | ...
    provider: str               # "ollama", "anthropic", ...
    model: str
    prompt_version: str         # "classify@3"
    confidence: float | None = None
    ai_run_id: int | None = None
    at: datetime


class ApplyResult(BaseModel):
    applied: list[str]          # field names written
    skipped_manual: list[str]   # fields skipped because they are in manual_fields


class IngestRequest(BaseModel):
    owner_id: int
    source: SourceInfo
    combine: bool = False       # several image files -> one PDF document
    shared: bool = True
    hints: dict[str, str] = {}  # free-form, passed through to the document.stored event


class IngestResult(BaseModel):
    document_id: str            # ULID, assigned immediately
    status: Literal["staged", "duplicate"]
    # duplicate: document_id is the EXISTING document; nothing new is created


class SearchFilters(BaseModel):
    categories: list[str] = []
    document_types: list[str] = []
    correspondents: list[str] = []
    tags: list[str] = []
    date_from: date | None = None        # on document_date
    date_to: date | None = None
    source_kinds: list[SourceKind] = []
    document_ids: list[str] = []         # restrict to these documents ("Ask about this document")
    include_trashed: bool = False


class KnowledgeBaseView(BaseModel):
    id: int
    name: str
    description: str
    filters: SearchFilters
    owner_id: int
    shared: bool
    local_only: bool
    created_at: datetime
    updated_at: datetime


class SemanticHit(BaseModel):
    document_id: str
    score: float                # cosine similarity, higher = better
    chunk_no: int
    text: str                   # best-matching chunk


class SearchHit(BaseModel):
    document_id: str
    title: str | None
    snippet: str | None         # plain text; highlights marked with \u0002 ... \u0003
    score: float                # fused score
    fts_rank: int | None        # 1-based rank in the FTS list, None if absent
    semantic_rank: int | None


class ChunkHit(BaseModel):
    """One retrieved chunk (knowledge-base retrieve, KB-02): RRF over chunk FTS and vectors."""

    document_id: str
    chunk_no: int
    text: str
    score: float  # fused score
    fts_rank: int | None  # 1-based rank in the chunk FTS list, None if absent
    semantic_rank: int | None
    title: str | None
    document_date: date | None
    category: str | None
    page: int | None = None
    url: str | None = None


class CurrentUser(BaseModel):
    id: int
    username: str
    role: Literal["admin", "member"]


class SetupCheck(BaseModel):
    """One item of the setup wizard / dashboard checklist (guided-experience skill)."""
    id: str                     # "vault", "ai.provider", "mail.accounts", ...
    area: Literal["storage", "ai", "mail", "capture", "notifications", "security", "backup"]
    title: str
    status: Literal["ok", "todo", "warn", "error", "optional"]
    message: str                # current state, one plain-language sentence
    action_label: str | None = None
    action_href: str | None = None   # app route, e.g. "/sources?connect=gmail"
    help_doc: str | None = None      # repo doc path, e.g. "docs/setup/mail-accounts.md"
    required: bool = False           # blocks "automation is ready"


# ---- Taxonomy (CL owns the loader; OA reads it) ----

class FactField(BaseModel):
    name: str                   # snake_case, unique within a document type
    type: FactType
    required: bool = False
    description: str = ""
    remind_days_before: list[int] = []   # CL reminders, e.g. [30, 7]


class Category(BaseModel):
    id: str                     # "utilities/electricity" (slash = hierarchy)
    label: str
    description: str = ""
    restricted: bool = False    # privacy: local AI only


class DocumentType(BaseModel):
    id: str                     # "invoice"
    label: str
    description: str = ""
    facts: list[FactField] = []


class Taxonomy(BaseModel):
    version: int
    languages: list[str]        # ISO 639-1, also drives OCR + FTS configs
    default_currency: str = "EUR"   # ISO 4217, used when a money fact has no currency
    categories: list[Category]
    document_types: list[DocumentType]
    tags: list[str]
```

---

## 2. Functions OA provides

Module paths are fixed. In OA-M0, OA creates the modules as **stubs** with these exact signatures,
each raising `NotImplementedError`. CL monkeypatches them in tests, or uses `tests/fakes/core.py`.

### 2.1 Config — `docuhive.config`
```python
def load_yaml(name: str) -> dict: ...
    # config/defaults/<name> deep-merged with $DOCUHIVE_OVERLAY_DIR/<name>.
    # Mappings merge recursively; lists and scalars from the overlay REPLACE the default.
    # Missing in both -> {}.
def overlay_path(*parts: str) -> Path | None: ...   # path inside the overlay if it exists
def prompt(name: str) -> tuple[str, str]: ...        # (text, version) for prompts/<name>.md, overlay wins
def plugins(hook: str) -> list[Callable]: ...        # entry points in group "docuhive.plugins" exposing <hook>
```
Prompt files start with front matter `---\nversion: 3\n---`. The version string returned is `"<name>@<version>"`.

### 2.2 Database — `docuhive.db`
```python
def session() -> ContextManager[Session]: ...  # SQLAlchemy 2 Session, commits on success, rolls back on error
CoreBase: type[DeclarativeBase]                 # OA tables
IntelBase: type[DeclarativeBase]                # CL tables (separate MetaData, separate Alembic env)
```

### 2.3 Jobs — `docuhive.jobs`
```python
def enqueue(kind: str, payload: dict, *, queue: str = "default",
            run_after: datetime | None = None, dedupe_key: str | None = None,
            in_session: Session | None = None) -> int: ...
    # dedupe_key: if a pending/running job with the same key exists, returns its id instead.
    # in_session: insert in the caller's transaction, so a state change and the job (or event)
    # it implies commit together or not at all.

def handler(kind: str, *, queue: str = "default", max_attempts: int = 5,
            timeout_s: int = 600) -> Callable: ...
    # decorator: def fn(payload: dict, ctx: JobContext) -> None

def periodic(kind: str, *, every: timedelta, queue: str = "default") -> Callable: ...
    # decorator: scheduler enqueues `kind` with payload {} every `every` (dedupe_key=kind)

class JobContext:
    job_id: int
    attempt: int                # 1-based
    log: logging.Logger
    def heartbeat(self) -> None: ...        # extend lease for long jobs
    def defer(self, until: datetime, reason: str) -> NoReturn: ...  # reschedule without counting an attempt

class RetryLater(Exception): ...            # raise to retry with backoff (counts an attempt)
class PermanentFailure(Exception): ...      # raise to fail immediately (status=dead)
```
- **Queues**: `ocr` (OA ingest), `ai` (CL agents), `mail` (CL connectors), `default`. The worker is started per queue set: `docuhive worker --queues ocr` or `--queues ai,mail,default`.
- **Unknown kind**: a job with no registered handler stays `pending`, is retried hourly, and is shown as "no handler" in the system UI. It never fails. This is what lets OA emit CL events before CL exists.
- **Handler registration**: handlers live in modules listed in `docuhive/worker/handlers.py` (`HANDLER_MODULES`, a shared touchpoint, append-only).

### 2.4 Ingest — `docuhive.ingest`
```python
def incoming_dir() -> Path: ...
    # temp dir on the same filesystem as staging; write files here, then submit (atomic move)
def submit(files: list[Path], req: IngestRequest) -> IngestResult: ...
    # Takes ownership of `files` (moves them). Validates type + size. Computes sha256.
    # Duplicate (owner_id, sha256) -> status "duplicate", existing document_id, files deleted.
    # Otherwise creates documents row (status=staged) and enqueues ingest.process.
    # len(files) > 1 requires combine=True and all images.
    # Raises UnsupportedType, TooLarge (both subclass IngestRejected) synchronously.
```
Supported types: PDF, JPEG, PNG, HEIC/HEIF, TIFF, WebP, DOCX, XLSX, PPTX, ODT, ODS, `.eml`, HTML (self-contained), TXT.
Max size is `DOCUHIVE_MAX_UPLOAD_MB` (default 100).

### 2.5 Documents — `docuhive.documents`
```python
def get(doc_id: str) -> DocumentView: ...                       # system use, no permission check
def get_for_user(doc_id: str, user: CurrentUser) -> DocumentView: ...  # raises NotFound if not visible
def get_content(doc_id: str, max_chars: int | None = None) -> str: ... # OCR/extracted text
def apply_metadata(doc_id: str, patch: MetadataPatch, *, actor: str,
                   provenance: Provenance | None = None, force: bool = False) -> ApplyResult: ...
def iter_ids(*, status: DocStatus = DocStatus.stored, added_since: datetime | None = None,
             filters: SearchFilters | None = None) -> Iterator[str]: ...
class NotFound(Exception): ...
```
`apply_metadata` semantics, all inside one transaction:
1. `actor` is `"user:<id>"`, `"ai:<task>"` or `"system"`.
2. With `actor="ai:*"` and `force=False`, fields in `manual_fields` are skipped (listed in `skipped_manual`).
3. With `actor="user:*"`, every written field is added to `manual_fields`.
4. Tags missing from the `tags` table are created. The correspondent is found by normalised name (casefold, trimmed, collapsed spaces) or created.
5. Writes `doc_facts`, updates the FTS vector, inserts an `audit_log` row (before/after), and re-renders `meta.json` in the vault (with `provenance` stored under `ai.<task>`).
6. `unlock_fields` (only with `actor="user:*"`) are removed from `manual_fields`, and listed as `unlocked` in the event payload so CL re-runs AI for them.
7. Enqueues `document.metadata_changed`.
8. **Category and document-type ids are not validated by OA.** CL validates against the taxonomy before calling.

### 2.6 Auth — `docuhive.auth`
```python
current_user: Callable[..., CurrentUser]      # FastAPI dependency (session cookie or Bearer token)
require_admin: Callable[..., CurrentUser]     # FastAPI dependency
def visible_docs(user: CurrentUser) -> ColumnElement[bool]: ...
    # SQL condition on core `documents` table:
    # (documents.owner_id == user.id OR documents.shared) AND documents.deleted_at IS NULL
    # Admins get the SAME rule (admin = operations, not data access).
def visible_docs_incl_trash(user: CurrentUser) -> ColumnElement[bool]: ...
```
Dev mode: if `DOCUHIVE_ENV=dev` and `DOCUHIVE_AUTH_DISABLED=true`, `current_user` returns `CurrentUser(id=1, username="dev", role="admin")`. The API refuses to start with `AUTH_DISABLED` in any other env.

### 2.7 Search — `docuhive.search`
```python
SemanticFn = Callable[[CurrentUser, str, SearchFilters, int], list[SemanticHit]]
def register_semantic(fn: SemanticFn) -> None: ...
def register_chunk_semantic(fn: SemanticFn) -> None: ...
def hybrid(user: CurrentUser, query: str, filters: SearchFilters,
           limit: int = 20, mode: Literal["hybrid", "fts", "semantic"] = "hybrid") -> list[SearchHit]: ...
def retrieve(user: CurrentUser, query: str, filters: SearchFilters,
             k: int = 20, mode: Literal["hybrid", "fts", "semantic"] = "hybrid") -> list[ChunkHit]: ...
```
- `hybrid` with no semantic function registered behaves as `fts`. `mode="semantic"` without one raises `SemanticUnavailable` (the API answers `400 semantic_unavailable`).
- Fusion is RRF with `k=60` over the top 50 of each list.
- Permissions and filters are applied in both lists. The semantic function **must** apply `visible_docs(user)` itself. `search.filters.conditions(filters)` is the one filter builder for both sides: ORed within a field, ANDed across fields.
- `retrieve` is the knowledge-base retrieval ([plan KB-M1](knowledge-bases.md#kb-m1-chunk-level-hybrid-retrieval-oa)): chunk FTS and the registered chunk semantic function (several chunks per document), fused, with at most 3 chunks per document. Only chunked (embedded) documents have chunks.

---

### 2.8 Knowledge bases — `docuhive.kb`
```python
def get(user: CurrentUser, kb_id: int) -> KnowledgeBaseView: ...
```
Missing and invisible bases both raise HTTP 404. Sharing a base never shares its
documents: every retrieval intersects its saved filters with `visible_docs(user)`.
Only the owner changes or deletes a base, including when the caller is an admin.

Authentication also supplies `request.state.token_id` (integer or `None`) and
`request.state.token_local_consumer` (boolean, false for browser sessions).
Tokens may have `kb:read` and `kb:ask` scopes. Only a browser session may issue a
token with `local_consumer=true`; bearer tokens cannot grant this flag, even with
the admin scope. CL applies restricted-document policy at its retrieval boundary.

## 3. Functions CL provides

| Function / file | Purpose | OA fallback |
|-----------------|---------|-------------|
| `docuhive.taxonomy.load() -> Taxonomy` (cached) and `docuhive.taxonomy.reload()` | taxonomy for UI filters, library view, FTS language list | parse `tests/fixtures/taxonomy.yaml` into `Taxonomy` |
| `config/defaults/taxonomy.yaml` | default taxonomy | fixture |
| `docuhive.ai.startup()` | called once by API and worker at startup (registers the semantic fn, handlers, plugins) | OA calls it inside `try/except ImportError` |
| `apps/web/components/intel/*.tsx` | slot components (see §7) | OA-created placeholders returning `null` |

---

## 4. Events (jobs emitted by OA, handled by CL)

OA enqueues these with `queue="ai"`. CL registers the handlers. Until CL does, they wait as "no handler" (§2.3).

| Kind | Payload | When |
|------|---------|------|
| `document.stored` | `{document_id, owner_id, source_kind, hints}` | after the vault write is verified and the DB commit is done (first time only) |
| `document.metadata_changed` | `{document_id, fields: [..], unlocked: [..], actor}` | after every `apply_metadata` that changed something |
| `document.quarantined` | `{document_id, owner_id, reason, source_kind}` | ingest failed |
| `document.trashed` / `document.restored` | `{document_id}` | soft delete / restore |
| `document.purged` | `{document_id}` | admin purge. CL must delete its rows for that document (chunks, review items) and null `ai_runs.document_id` |

Payload `hints` is `IngestRequest.hints` passed through (e.g. `{"doc_hint": "invoice"}` from email triage).

---

## 5. Database ownership

There are two Alembic environments in one Postgres database: `migrations/core` (OA, version table `alembic_version_core`) and `migrations/intel` (CL, version table `alembic_version_intel`).
`docuhive db upgrade` runs core first, then intel. Intel migrations may add foreign keys to core tables with `op.create_foreign_key`; intel ORM models declare plain columns.

**Read rule:** either track may **read** any table via SQLAlchemy Core/ORM. **Write rule:** writes only to your own tables; the other track's state is changed through contracts only.

### 5.1 Core tables (OA): schema that CL reads

```sql
CREATE TABLE users (
  id            bigserial PRIMARY KEY,
  username      text UNIQUE NOT NULL,
  pw_hash       text NOT NULL,
  role          text NOT NULL CHECK (role IN ('admin','member')),
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE documents (
  id                text PRIMARY KEY,               -- ULID
  owner_id          bigint NOT NULL REFERENCES users(id),
  shared            boolean NOT NULL DEFAULT true,
  status            text NOT NULL,                  -- DocStatus
  sha256            text NOT NULL,
  mime              text NOT NULL,
  pages             int,
  vault_path        text,                           -- relative, e.g. 2026/01JC.../
  title             text,
  document_date     date,
  language          text,
  fts_config        regconfig NOT NULL DEFAULT 'dh_simple',
  category          text,
  document_type     text,
  correspondent_id  bigint REFERENCES correspondents(id),
  content           text,
  content_tsv       tsvector,
  manual_fields     text[] NOT NULL DEFAULT '{}',
  quarantine_reason text,
  added_at          timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  deleted_at        timestamptz,
  UNIQUE (owner_id, sha256)
);

CREATE TABLE correspondents (id bigserial PRIMARY KEY, name text NOT NULL, norm_name text UNIQUE NOT NULL, merged_into bigint);
CREATE TABLE tags (id bigserial PRIMARY KEY, name text NOT NULL, slug text UNIQUE NOT NULL, merged_into bigint);
CREATE TABLE document_tags (document_id text REFERENCES documents(id), tag_id bigint REFERENCES tags(id), PRIMARY KEY (document_id, tag_id));

CREATE TABLE doc_facts (
  document_id  text REFERENCES documents(id),
  field        text NOT NULL,
  type         text NOT NULL,          -- FactType
  value_text   text NOT NULL,          -- canonical string (always set)
  value_num    numeric,                -- money/number
  value_date   date,                   -- date
  currency     text,
  confidence   real,
  PRIMARY KEY (document_id, field)
);

CREATE TABLE doc_sources (
  document_id text PRIMARY KEY REFERENCES documents(id),
  kind text NOT NULL, original_filename text NOT NULL,
  account_id bigint, message_id text, email_from text, subject text, received_at timestamptz
);
```
Other core tables (CL does not need them): `sessions`, `api_tokens`, `notes`, `audit_log`, `jobs`, `settings`.

`knowledge_bases` is core-owned and readable through `kb.get`: integer `id`, text
`name`, `description`, JSONB `filters`, `owner_id` referencing users, boolean
`shared` (default false), `local_only` (default true), and `created_at`/`updated_at`.
`api_tokens.local_consumer` is boolean, false by default.

### 5.2 Intel tables (CL)
`mail_accounts`, `mail_messages`, `mail_attachments`, `backfills`, `ai_runs`, `review_items`, `doc_chunks`, `chat_sessions`, `chat_messages`, `analyses`, `reminders`, `notification_channels`. Schemas are in the CL plan files. OA reads `doc_chunks` by its shared columns for retrieval and knowledge-base status; other intel tables are accessed through CL's API/UI.

---

## 6. HTTP API ownership

The base path is `/api`. There is one FastAPI app. Routers are listed in `docuhive/api/routers.py` (`ROUTERS`, a shared touchpoint, append-only).

| Prefix | Owner |
|--------|-------|
| `/api/auth/*`, `/api/users/*`, `/api/tokens/*` | OA |
| `/api/documents/*`, `/api/upload`, `/api/search` | OA |
| `/api/kb`, `/api/kb/{id}`, `/api/kb/{id}/status`, `/api/kb/suggestions`, `/api/kb/options` | OA |
| `/api/kb/{id}/retrieve`, `/api/kb/{id}/ask` | CL |
| `/api/vocabulary/*` (tags, correspondents) | OA |
| `/api/system/*` (health, vault, jobs, quarantine, stats, `sse-test`, `setup-status`) | OA |
| `/api/taxonomy` | CL |
| `/api/ai/*` (providers, routing, runs, usage, similar) | CL |
| `/api/review/*` | CL |
| `/api/sources/*` (mail accounts, OAuth, backfills, triage log) | CL |
| `/api/chat/*`, `/api/analyses/*`, `/api/reminders/*` | CL |
| `/api/notifications/*` | CL |
| `GET /api/system/setup-status`, `GET /api/ai/setup-status`, `GET /api/sources/setup-status`, `GET /api/notifications/setup-status` | each owner → `list[SetupCheck]` (OA's `/setup` page and dashboard merge all four) |

**Conventions** (both tracks):
- JSON bodies with `snake_case`. ISO-8601 dates. Document ids are ULID strings; other ids are integers.
- Errors: HTTP status + `{"error": {"code": "not_found", "message": "…", "details": {}}}`.
- Lists use cursor pagination: `?limit=50&cursor=…` → `{"items": [...], "next_cursor": "…" | null}`.
- Every endpoint depends on `auth.current_user` unless it is explicitly public (`/api/auth/login`, `/api/system/health`).
- Streaming (chat) uses `text/event-stream` and passes through the Next proxy unbuffered (OA guarantees this, verified with `/api/system/sse-test`).
- The OpenAPI schema is exported with `docuhive openapi > apps/web/lib/api/openapi.json`, and the TS types are generated with `npm run gen:api` (openapi-typescript). Generated files are committed. On a merge conflict, regenerate instead of hand-merging.

---

## 7. Web ownership (`apps/web`)

OA owns `/knowledge` (saved scopes and indexing status); CL owns its retrieval test
panel and Ask scope integration. OA owns `/settings/tokens`, including KB scopes.

| Path | Owner |
|------|-------|
| `app/layout.tsx`, `app/(auth)/login`, `app/(app)/layout.tsx` (shell, nav, auth guard), `middleware.ts` | OA |
| `app/api/[...path]/route.ts` (BFF proxy) | OA |
| `app/(app)/page.tsx` (dashboard), `setup/` (wizard), `documents/`, `search/`, `upload/`, `capture/`, `quarantine/`, `vocabulary/`, `settings/{account,users,tokens,system}`, `dev/ui/` (kitchen sink, dev only), the ⌘K command palette in the shell | OA |
| `app/(app)/review/`, `ask/`, `analyses/`, `sources/`, `reminders/`, `settings/ai/` (incl. `runs/[id]` "Under the hood"), `settings/notifications/` | CL |
| `app/globals.css` (design tokens), `lib/ui/control.ts` | OA, following the `docuhive-ui` skill. CL uses them and never overrides them |
| `components/ui/*` (shadcn), `lib/api/*` (client + generated types), `lib/nav.ts` | OA (`lib/nav.ts` is a shared touchpoint, append-only) |
| `components/core/*` | OA |
| `components/intel/*` | CL |

**Slots** (OA renders them; CL implements them):

| File | Props | Where OA renders it |
|------|-------|---------------------|
| `components/intel/DashboardWidgets.tsx` exporting `IntelDashboardWidgets` | `{}` | dashboard grid, after the core widgets |
| `components/intel/DocumentAIPanel.tsx` | `{ documentId: string }` | document detail, right column |
| `components/intel/SimilarDocuments.tsx` | `{ documentId: string }` | document detail, below the metadata |
| `components/intel/SearchModeHint.tsx` | `{ semanticAvailable: boolean }` | search page, under the query box |
| `components/intel/SetupSteps.tsx` exporting `intelSetupSteps: { id: string; title: string; Component: React.FC<{ onDone(): void }> }[]` | — | the `/setup` wizard renders these steps (AI provider, models, privacy, email, notifications) between OA's storage and phone steps |

OA creates each file in OA-M5 as `export function X() { return null }`. From then on the file belongs to CL.

---

## 8. Environment variables

| Prefix | Owner | Examples |
|--------|-------|----------|
| `DOCUHIVE_` | OA | `DATABASE_URL`, `VAULT_DIR`, `STAGING_DIR`, `SECRET_KEY`, `OVERLAY_DIR`, `ENV`, `AUTH_DISABLED`, `MAX_UPLOAD_MB`, `API_URL` (web), `PUBLIC_URL` |
| `DOCUHIVE_AI_` | CL | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OLLAMA_HOST`, `AWS_PROFILE`, `AWS_REGION` |
| `DOCUHIVE_MAIL_` | CL | `TOKEN_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET` |

Each track has its own `pydantic-settings` class in its own module (`docuhive/config/settings.py` for OA, `docuhive/ai/settings.py` and `docuhive/mail/settings.py` for CL). `.env.example` is a shared touchpoint, with one section per prefix.

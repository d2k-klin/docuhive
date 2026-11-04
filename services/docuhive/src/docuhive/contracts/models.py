from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

CONTRACT_VERSION = 1

FactType = Literal["money", "date", "string", "number", "iban"]


class SourceKind(StrEnum):
    upload = "upload"  # web UI upload
    mobile = "mobile"  # PWA capture
    email = "email"  # CL mail connectors
    consume = "consume"  # scanner drop folder
    api = "api"  # personal API token (scripts, iOS Shortcuts)


class SourceInfo(BaseModel):
    kind: SourceKind
    original_filename: str
    account_id: int | None = None  # mail_accounts.id (CL table), email only
    message_id: str | None = None  # provider message id, email only
    email_from: str | None = None
    subject: str | None = None
    received_at: datetime | None = None


class DocStatus(StrEnum):
    staged = "staged"  # accepted, waiting for processing
    processing = "processing"  # convert / OCR running
    stored = "stored"  # in the vault, searchable
    quarantined = "quarantined"  # failed; input kept, retry possible


class FactValue(BaseModel):
    type: FactType
    value: str  # canonical string: money "84.20", date "2026-11-20", number "12.5"
    currency: str | None = None  # ISO 4217, money only
    confidence: float | None = Field(default=None, ge=0, le=1)


class DocumentView(BaseModel):
    id: str  # ULID
    owner_id: int
    shared: bool
    status: DocStatus
    mime: str  # mime of the original
    pages: int | None
    added_at: datetime
    title: str | None
    document_date: date | None
    language: str | None  # ISO 639-1, e.g. "de"
    category: str | None  # taxonomy category id, e.g. "utilities/electricity"
    document_type: str | None  # taxonomy document type id, e.g. "invoice"
    correspondent: str | None  # display name
    tags: list[str]
    facts: dict[str, FactValue]
    manual_fields: list[str]  # fields a user set; AI must not overwrite
    source: SourceInfo
    deleted_at: datetime | None


class MetadataPatch(BaseModel):
    """None = leave unchanged. Facts merge per key; a fact set to None is removed."""

    title: str | None = None
    document_date: date | None = None
    language: str | None = None
    category: str | None = None
    document_type: str | None = None
    correspondent: str | None = None  # find-or-create by normalised name
    tags_add: list[str] = []
    tags_remove: list[str] = []
    facts: dict[str, FactValue | None] | None = None
    unlock_fields: list[str] = []  # user only: remove from manual_fields ("let AI manage again")


class Provenance(BaseModel):
    task: str  # "classify" | "extract" | ...
    provider: str  # "ollama", "anthropic", ...
    model: str
    prompt_version: str  # "classify@3"
    confidence: float | None = None
    ai_run_id: int | None = None
    at: datetime


class ApplyResult(BaseModel):
    applied: list[str]  # field names written
    skipped_manual: list[str]  # fields skipped because they are in manual_fields


class IngestRequest(BaseModel):
    owner_id: int
    source: SourceInfo
    combine: bool = False  # several image files -> one PDF document
    shared: bool = True
    hints: dict[str, str] = {}  # free-form, passed through to the document.stored event


class IngestResult(BaseModel):
    document_id: str  # ULID, assigned immediately
    status: Literal["staged", "duplicate"]
    # duplicate: document_id is the EXISTING document; nothing new is created


class SearchFilters(BaseModel):
    categories: list[str] = []
    document_types: list[str] = []
    correspondents: list[str] = []
    tags: list[str] = []
    date_from: date | None = None  # on document_date
    date_to: date | None = None
    source_kinds: list[SourceKind] = []
    document_ids: list[str] = []  # restrict to these documents ("Ask about this document")
    include_trashed: bool = False


class SemanticHit(BaseModel):
    document_id: str
    score: float  # cosine similarity, higher = better
    chunk_no: int
    text: str  # best-matching chunk


class SearchHit(BaseModel):
    document_id: str
    title: str | None
    snippet: str | None  # plain text; highlights marked with \u0002 ... \u0003
    score: float  # fused score
    fts_rank: int | None  # 1-based rank in the FTS list, None if absent
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


class CurrentUser(BaseModel):
    id: int
    username: str
    role: Literal["admin", "member"]


class SetupCheck(BaseModel):
    """One item of the setup wizard / dashboard checklist (guided-experience skill)."""

    id: str  # "vault", "ai.provider", "mail.accounts", ...
    area: Literal["storage", "ai", "mail", "capture", "notifications", "security", "backup"]
    title: str
    status: Literal["ok", "todo", "warn", "error", "optional"]
    message: str  # current state, one plain-language sentence
    action_label: str | None = None
    action_href: str | None = None  # app route, e.g. "/sources?connect=gmail"
    help_doc: str | None = None  # repo doc path, e.g. "docs/setup/mail-accounts.md"
    required: bool = False  # blocks "automation is ready"


# ---- Taxonomy (CL owns the loader; OA reads it) ----


class FactField(BaseModel):
    name: str  # snake_case, unique within a document type
    type: FactType
    required: bool = False
    description: str = ""
    remind_days_before: list[int] = []  # CL reminders, e.g. [30, 7]


class Category(BaseModel):
    id: str  # "utilities/electricity" (slash = hierarchy)
    label: str
    description: str = ""
    restricted: bool = False  # privacy: local AI only


class DocumentType(BaseModel):
    id: str  # "invoice"
    label: str
    description: str = ""
    facts: list[FactField] = []


class Taxonomy(BaseModel):
    version: int
    languages: list[str]  # ISO 639-1, also drives OCR + FTS configs
    default_currency: str = "EUR"  # ISO 4217, used when a money fact has no currency
    categories: list[Category]
    document_types: list[DocumentType]
    tags: list[str]

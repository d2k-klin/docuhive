"""Classify agent: category, type, correspondent, tags, title, date, language (CLS-01..05)."""

import re
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from docuhive import db, documents, taxonomy
from docuhive.agents import validators
from docuhive.agents.base import StructuredResult, run_structured
from docuhive.ai import coretables, routing
from docuhive.contracts import DocumentView, Provenance, Taxonomy
from docuhive.review import Suggestion, apply_suggestions, suggest

FIELDS = (
    "title",
    "category",
    "document_type",
    "correspondent",
    "tags",
    "document_date",
    "language",
)
NEW_CORRESPONDENT_MAX_CONFIDENCE = 0.7


class NewTerm(BaseModel):
    kind: Literal["category", "document_type", "tag"]
    value: str
    reason: str = ""


class ClassifyOut(BaseModel):
    title: str = Field(max_length=120, description="human title in the document language")
    category: str = Field(description="category id from the list")
    document_type: str = Field(description="document type id from the list")
    correspondent: str | None = Field(description="issuer or sender, organisation or person")
    tags: list[str] = []
    document_date: date | None = Field(description="issue date printed on the document")
    language: str = Field(description="ISO 639-1 code")
    confidence: dict[str, float] = Field(description="0..1 per field")
    proposed_new_terms: list[NewTerm] = []
    reasoning: str = Field(default="", max_length=400)


def head_tail(text: str, head: int, tail: int) -> str:
    if len(text) <= head + tail:
        return text
    return f"{text[:head]}\n…\n{text[-tail:]}"


def top_correspondents(limit: int = 200) -> list[str]:
    c, d = coretables.table("correspondents"), coretables.table("documents")
    q = (
        select(c.c.name)
        .join(d, d.c.correspondent_id == c.c.id, isouter=True)
        .where(c.c.merged_into.is_(None))
        .group_by(c.c.id, c.c.name)
        .order_by(func.count(d.c.id).desc(), c.c.name)
        .limit(limit)
    )
    with db.session() as s:
        return list(s.scalars(q))


def variables(
    view: DocumentView, content: str, tax: Taxonomy, known: list[str], hints: dict | None = None
) -> dict:
    ctx = routing.load().tasks["classify"].context
    src = view.source
    return {
        "categories": "\n".join(
            f"- {c.id} — {c.label}" + (f": {c.description}" if c.description else "")
            for c in tax.categories
        ),
        "document_types": "\n".join(f"- {t.id} — {t.label}" for t in tax.document_types),
        "tags": ", ".join(tax.tags) or "(none)",
        "correspondents": "\n".join(f"- {n}" for n in known) or "(none yet)",
        "filename": src.original_filename,
        "source": src.kind,
        "subject": src.subject or "-",
        "email_from": src.email_from or "-",
        "doc_hint": (hints or {}).get("doc_hint") or "-",
        "content": head_tail(content, ctx.get("head_chars", 6000), ctx.get("tail_chars", 1500)),
    }


def make_validator(tax: Taxonomy, known: list[str], today: date | None = None):  # type: ignore[no-untyped-def]
    categories = {c.id for c in tax.categories}
    types = {t.id for t in tax.document_types}

    def validate(out: ClassifyOut) -> ClassifyOut:
        out = out.model_copy(deep=True)
        errors = []
        if out.category not in categories:
            errors.append(f"category {out.category!r} is not one of the listed ids")
        if out.document_type not in types:
            errors.append(f"document_type {out.document_type!r} is not one of the listed ids")
        out.language = out.language.strip().lower()
        if not re.fullmatch(r"[a-z]{2}", out.language):
            errors.append(f"language {out.language!r} must be an ISO 639-1 code like 'de'")
        if errors:
            raise ValueError("; ".join(errors))
        unknown = [t for t in out.tags if t not in tax.tags]
        out.tags = [t for t in out.tags if t in tax.tags]
        out.proposed_new_terms += [
            NewTerm(kind="tag", value=t, reason="suggested tag")
            for t in unknown
            if t not in {n.value for n in out.proposed_new_terms}
        ]
        if out.document_date:
            try:
                validators.check_date_range(out.document_date, today)
            except validators.Invalid:
                out.document_date = None
                out.confidence["document_date"] = 0.0
        if out.correspondent:
            name = validators.clean_string(out.correspondent)
            match = next(
                (k for k in known if validators.norm_name(k) == validators.norm_name(name)), None
            ) or validators.best_match(name, known)
            if match:
                out.correspondent = match
            else:
                out.correspondent = name
                out.confidence["correspondent"] = min(
                    out.confidence.get("correspondent", 0.0), NEW_CORRESPONDENT_MAX_CONFIDENCE
                )
        return out

    return validate


def suggestions(out: ClassifyOut) -> list[Suggestion]:
    conf = out.confidence
    values = {
        "title": out.title.strip(),
        "category": out.category,
        "document_type": out.document_type,
        "correspondent": out.correspondent,
        "tags": out.tags,
        "document_date": out.document_date.isoformat() if out.document_date else None,
        "language": out.language,
    }
    return [
        Suggestion(
            field=f, payload={"value": v}, confidence=conf.get(f), reason=out.reasoning or None
        )
        for f, v in values.items()
        if v not in (None, [], "")
    ]


def provenance(res: StructuredResult, task: str, confidence: float | None) -> Provenance:
    return Provenance(
        task=task,
        provider=res.route.provider,
        model=res.route.model,
        prompt_version=res.prompt_version,
        confidence=confidence,
        ai_run_id=res.ai_run_id,
        at=datetime.now(UTC),
    )


def classify(doc_id: str, hints: dict | None = None) -> dict:
    """Run, validate and apply (or queue for review). Returns a summary for the pipeline."""
    view = documents.get(doc_id)
    tax = taxonomy.load()
    known = top_correspondents()
    content = documents.get_content(doc_id)
    res = run_structured(
        "classify",
        "classify",
        variables(view, content, tax, known, hints),
        ClassifyOut,
        document=view,
        validate=make_validator(tax, known),
    )
    out = res.value
    policy = routing.load().tasks["classify"].apply
    applied = apply_suggestions(
        view,
        suggestions(out),
        policy,
        provenance(res, "classify", out.confidence.get("category")),
        always_apply=("language",),
    )
    for term in out.proposed_new_terms:
        suggest(
            doc_id,
            Suggestion(
                field=f"{term.kind}:{term.value}",
                payload={"value": term.value},
                confidence=None,
                reason=term.reason or None,
            ),
            ai_run_id=res.ai_run_id,
            kind="new_term",
        )
    return {
        "ai_run_id": res.ai_run_id,
        "applied": applied,
        "document_type": out.document_type,
        "category": out.category,
    }

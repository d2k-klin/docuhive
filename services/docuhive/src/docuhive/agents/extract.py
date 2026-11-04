"""Extract agent: typed facts per document type (amounts, dates, IBANs...), validated in code."""

from collections import Counter
from dataclasses import dataclass

from pydantic import BaseModel, Field, create_model

from docuhive import documents, taxonomy
from docuhive.agents import validators
from docuhive.agents.base import StructuredResult, run_structured
from docuhive.agents.classify import head_tail, provenance
from docuhive.ai import routing
from docuhive.contracts import DocumentType, DocumentView, Taxonomy
from docuhive.review import Suggestion, apply_suggestions, suggest


class Fact(BaseModel):
    value: str | None = None
    confidence: float = 0.0
    evidence: str | None = Field(default=None, max_length=120)


class MoneyFact(Fact):
    currency: str | None = None


def output_model(dt: DocumentType) -> type[BaseModel]:
    """A schema built from taxonomy.document_types[type].facts."""
    fields = {
        f.name: (
            MoneyFact if f.type == "money" else Fact,
            Field(
                default_factory=MoneyFact if f.type == "money" else Fact,
                description=f.description or f.type,
            ),
        )
        for f in dt.facts
    }
    return create_model(f"Extract_{dt.id.replace('-', '_')}", **fields)  # type: ignore[call-overload]


def context_currency(content: str, default: str) -> str:
    codes = Counter(c for c in (validators.currency_of(line) for line in content.splitlines()) if c)
    return codes.most_common(1)[0][0] if codes else default


@dataclass
class Extracted:
    res: StructuredResult
    facts: list[Suggestion]  # valid, canonical facts ("facts.<name>")
    problems: list[Suggestion]  # missing required / invalid values, for review


def run_extract(
    dt: DocumentType,
    content: str,
    tax: Taxonomy,
    *,
    document: DocumentView | None = None,
    restricted: bool | None = None,
) -> Extracted:
    """Model call + validation, without touching document state (also used by evals)."""
    limit = routing.load().tasks["extract"].context.get("max_chars", 12000)
    facts_doc = "\n".join(
        f"- {f.name} ({f.type}{', required' if f.required else ''})"
        + (f": {f.description}" if f.description else "")
        for f in dt.facts
    )
    res = run_structured(
        "extract",
        "extract",
        {
            "document_type": dt.id,
            "document_type_label": dt.label,
            "facts": facts_doc,
            "content": head_tail(content, int(limit * 0.75), int(limit * 0.25)),
        },
        output_model(dt),
        document=document,
        restricted=restricted,
    )
    default_cur = context_currency(content, tax.default_currency)
    good: list[Suggestion] = []
    problems: list[Suggestion] = []
    for f in dt.facts:
        raw: Fact = getattr(res.value, f.name)
        field = f"facts.{f.name}"
        if not raw.value:
            if f.required:
                problems.append(
                    Suggestion(
                        field=field,
                        payload={"value": None, "type": f.type},
                        confidence=0.0,
                        reason="missing required fact",
                    )
                )
            continue
        try:
            value, cur = validators.canonical(
                f.type, raw.value, getattr(raw, "currency", None), default_currency=default_cur
            )
        except validators.Invalid as e:
            problems.append(
                Suggestion(
                    field=field,
                    payload={"value": None, "type": f.type, "raw": raw.value},
                    confidence=0.0,
                    reason=f"invalid: {e}",
                    evidence=raw.evidence,
                )
            )
            continue
        payload = {"value": value, "type": f.type, "confidence": raw.confidence}
        if cur:
            payload["currency"] = cur
        good.append(
            Suggestion(
                field=field, payload=payload, confidence=raw.confidence, evidence=raw.evidence
            )
        )
    return Extracted(res, good, problems)


def extract(doc_id: str, document_type: str | None = None) -> dict:
    view = documents.get(doc_id)
    tax = taxonomy.load()
    dt = taxonomy.document_type(tax, document_type or view.document_type)
    if dt is None or not dt.facts:
        return {"skipped": "document type has no facts"}
    out = run_extract(dt, documents.get_content(doc_id), tax, document=view)
    for p in out.problems:
        suggest(doc_id, p, ai_run_id=out.res.ai_run_id)
    policy = routing.load().tasks["extract"].apply
    applied = apply_suggestions(view, out.facts, policy, provenance(out.res, "extract", None))
    return {
        "ai_run_id": out.res.ai_run_id,
        "applied": applied,
        "facts": [s.field for s in out.facts],
    }

"""Triage agent: a cheap gatekeeper on the envelope before the expensive pipeline (MAIL-04).

Input is from/subject/labels/attachment list and a 2 KB text snippet. Never attachment content.
"""

from pydantic import BaseModel, Field

from docuhive import taxonomy
from docuhive.agents.base import StructuredResult, run_structured
from docuhive.ai import privacy, routing
from docuhive.mail.base import AttachmentMeta, MailMessage


class TriageOut(BaseModel):
    archive: bool
    attachments: list[str] = Field(default=[], description="file names to import")
    archive_body: bool = False
    doc_hint: str | None = None
    reason: str = Field(default="", max_length=200)
    confidence: float = Field(ge=0, le=1)


def triage(m: MailMessage, candidates: list[AttachmentMeta]) -> StructuredResult[TriageOut]:
    tax = taxonomy.load()
    names = {a.filename for a in candidates}
    types = {t.id for t in tax.document_types}

    def validate(out: TriageOut) -> TriageOut:
        out = out.model_copy()
        out.attachments = [a for a in out.attachments if a in names]  # never more than offered
        if out.doc_hint not in types:
            out.doc_hint = None
        return out

    variables = {
        "email_from": m.email_from,
        "subject": m.subject or "(no subject)",
        "received": m.ref.received_at.date().isoformat(),
        "labels": ", ".join(m.labels) or "-",
        "attachments": "\n".join(
            f"- {a.filename} ({a.mime}, {(a.size or 0) // 1024} KB)" for a in candidates
        )
        or "(none)",
        "snippet": m.text_snippet[:2048] or "(empty)",
        "document_types": ", ".join(sorted(types)),
    }
    # Snippets are not documents: privacy.local_only still applies through the router.
    return run_structured(
        "triage",
        "triage",
        variables,
        TriageOut,
        validate=validate,
        restricted=privacy.is_restricted(None, tax),
    )


def accept_threshold() -> float:
    return routing.load().tasks["triage"].accept_threshold


def triage_is_local() -> bool:
    """For the connect-time warning: are email snippets sent to a cloud model?"""
    from docuhive.ai import router

    routes = router.resolve("triage", restricted=False)
    return bool(routes) and routes[0].local

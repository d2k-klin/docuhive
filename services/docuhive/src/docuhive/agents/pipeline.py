"""Job handlers that turn OA's document events into AI work (queue "ai").

document.stored -> ai.classify -> ai.extract (if the type has facts) -> index.embed + reminders
Every step is idempotent (dedupe keys) and handles the harness outcomes explicitly.
"""

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import delete, update

from docuhive import db, fields, jobs, taxonomy
from docuhive.agents.base import AIDisabled, AllRoutesFailed, InvalidOutput
from docuhive.ai.budgets import BudgetExceeded, next_month_start
from docuhive.ai.privacy import NoAllowedRoute
from docuhive.ai.router import ProviderUnavailable
from docuhive.review import notice, supersede

log = logging.getLogger(__name__)
CLASSIFY_FIELDS = {
    "title",
    "category",
    "document_type",
    "correspondent",
    "tags",
    "document_date",
    "language",
}
EMBED_FIELDS = {"title", "correspondent", "category", "document_type", "document_date"}


def is_fact(field: str) -> bool:
    return field == "facts" or field.startswith("facts.")


def enqueue_doc(kind: str, doc_id: str, **extra: Any) -> int:
    short = {
        "ai.classify": "classify",
        "ai.extract": "extract",
        "index.embed": "embed",
        "reminders.sync": "reminders",
    }[kind]
    return jobs.enqueue(
        kind, {"document_id": doc_id, **extra}, queue="ai", dedupe_key=f"{short}:{doc_id}"
    )


def guarded(doc_id: str, ctx: Any, fn: Callable[..., dict], *args: Any) -> dict | None:
    """Run an AI step; map harness outcomes to queue behaviour. None = step did not complete."""
    try:
        return fn(*args)
    except AIDisabled:
        ctx.log.info("AI disabled; skipping %s", doc_id)
    except NoAllowedRoute as e:
        notice(doc_id, f"AI skipped: {e.reason}")
    except InvalidOutput as e:
        notice(doc_id, f"AI could not produce a valid answer ({e}). See Settings → AI → Runs.")
    except ProviderUnavailable as e:
        notice(doc_id, f"AI provider unavailable: {e}")
    except BudgetExceeded as e:
        ctx.defer(next_month_start(), f"budget: {e}")
    except AllRoutesFailed as e:
        raise jobs.RetryLater(str(e)) from e
    return None


@jobs.handler("document.stored", queue="ai")
def on_stored(payload: dict, ctx: Any) -> None:
    from docuhive.mail import ledger

    doc_id = payload["document_id"]
    ledger.on_document(doc_id, "stored")
    hints = payload.get("hints") or {}
    if hints.get("rebuild") == "true":  # vault rebuild: metadata already known, only re-index
        enqueue_doc("index.embed", doc_id)
    else:
        enqueue_doc("ai.classify", doc_id, hints=hints)


@jobs.handler("ai.classify", queue="ai", timeout_s=900)
def run_classify(payload: dict, ctx: Any) -> None:
    from docuhive.agents.classify import classify

    doc_id = payload["document_id"]
    summary = guarded(doc_id, ctx, classify, doc_id, payload.get("hints"))
    if summary is None:
        return
    dt = fields.document_type(taxonomy.load(), summary["document_type"])
    if dt and dt.facts:
        enqueue_doc("ai.extract", doc_id, document_type=dt.id)
    else:
        enqueue_doc("index.embed", doc_id)


@jobs.handler("ai.extract", queue="ai", timeout_s=900)
def run_extract(payload: dict, ctx: Any) -> None:
    from docuhive.agents.extract import extract

    doc_id = payload["document_id"]
    if guarded(doc_id, ctx, extract, doc_id, payload.get("document_type")) is not None:
        enqueue_doc("reminders.sync", doc_id)
    enqueue_doc("index.embed", doc_id)


@jobs.handler("document.metadata_changed", queue="ai")
def on_metadata_changed(payload: dict, ctx: Any) -> None:
    doc_id, actor = payload["document_id"], payload.get("actor", "system")
    fields: list[str] = payload.get("fields") or []
    unlocked: list[str] = payload.get("unlocked") or []
    if not actor.startswith("ai:"):
        supersede(doc_id, fields)  # a person decided: their value replaces pending suggestions
    if actor.startswith("user:") and "document_type" in fields:
        enqueue_doc("ai.extract", doc_id)
    if CLASSIFY_FIELDS & set(unlocked):
        enqueue_doc("ai.classify", doc_id)
    if any(is_fact(f) for f in unlocked):
        enqueue_doc("ai.extract", doc_id)
    if EMBED_FIELDS & set(fields):
        enqueue_doc("index.embed", doc_id)
    if any(is_fact(f) for f in fields):
        enqueue_doc("reminders.sync", doc_id)


@jobs.handler("document.quarantined", queue="ai")
def on_quarantined(payload: dict, ctx: Any) -> None:
    from docuhive.mail import ledger
    from docuhive.notify import Notification, send

    doc_id = payload["document_id"]
    ledger.on_document(doc_id, "quarantined", payload.get("reason"))
    send(
        Notification(
            kind="quarantine",
            title="A document could not be processed",
            body=f"Reason: {payload.get('reason') or 'unknown'}. "
            "The original is kept; you can retry it.",
            url="/quarantine",
            priority="high",
            user_id=payload.get("owner_id"),
        )
    )


@jobs.handler("document.trashed", queue="ai")
@jobs.handler("document.restored", queue="ai")
def on_visibility(payload: dict, ctx: Any) -> None:
    """Nothing to do: every CL query applies visible_docs, which excludes trashed documents."""


@jobs.handler("document.purged", queue="ai")
def on_purged(payload: dict, ctx: Any) -> None:
    """Delete CL rows for the document (FKs cascade in Postgres; this also covers SQLite)."""
    from docuhive.ai.models import AIRun
    from docuhive.index.models import DocChunk
    from docuhive.reminders.models import Reminder
    from docuhive.review.models import ReviewItem

    doc_id = payload["document_id"]
    with db.session() as s:
        for model in (ReviewItem, DocChunk, Reminder):
            s.execute(delete(model).where(model.document_id == doc_id))
        s.execute(update(AIRun).where(AIRun.document_id == doc_id).values(document_id=None))

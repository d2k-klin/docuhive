"""Document AI progress derived from the durable queue, run log and unapplied suggestions."""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from docuhive import auth, db, jobs, taxonomy
from docuhive.ai import coretables
from docuhive.ai.http import User
from docuhive.ai.models import AIRun
from docuhive.ai.settings import get_ai_settings
from docuhive.review.models import ReviewItem


class ProgressRequest(BaseModel):
    document_ids: list[Annotated[str, Field(min_length=1, max_length=26)]] = Field(max_length=500)


def document_status(body: ProgressRequest, user: User) -> dict:
    d = coretables.table("documents")
    with db.session() as s:
        visible = s.execute(
            select(d.c.id, d.c.category, d.c.status).where(
                d.c.id.in_(body.document_ids),
                auth.visible_docs(user),
            )
        ).all()
        ids = [r.id for r in visible]
        runs = list(
            s.execute(
                select(AIRun.document_id, AIRun.task, AIRun.status, AIRun.id)
                .where(
                    AIRun.document_id.in_(ids),
                    AIRun.task.in_(("classify", "extract", "embed")),
                )
                .order_by(AIRun.id.desc())
            )
        )
        pending = list(
            s.execute(
                select(
                    ReviewItem.document_id, ReviewItem.field, ReviewItem.suggested, ReviewItem.kind
                ).where(
                    ReviewItem.document_id.in_(ids),
                    ReviewItem.status == "pending",
                )
            )
        )
    by_job: dict[str, dict[str, dict]] = defaultdict(dict)
    for job in jobs.document_jobs(ids):
        by_job[job["document_id"]].setdefault(job["kind"], job)
    by_run: dict[str, dict[str, Any]] = defaultdict(dict)
    for run in runs:
        by_run[run.document_id].setdefault(run.task, run)
    by_review: dict[str, list[Any]] = defaultdict(list)
    for item in pending:
        by_review[item.document_id].append(item)
    labels = {c.id: c.label for c in taxonomy.load().categories}
    enabled = get_ai_settings().enabled
    now = datetime.now(UTC)
    items = []
    for doc in visible:
        queue = by_job[doc.id]
        cutoff = queue.get("ai.classify", {}).get("id", 0)
        current = [j for j in queue.values() if j["id"] >= cutoff]
        active = [j for j in current if j["status"] in ("running", "pending", "deferred")]
        latest = by_run[doc.id]
        stage = None
        if doc.status != "stored":
            state = "processing" if doc.status != "quarantined" else "failed"
        elif not enabled:
            state = "disabled"
        elif active:
            job = next((j for j in active if j["status"] == "running"), active[0])
            stage = job["kind"]
            when = job.get("run_after")
            if when and when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            state = (
                "running"
                if job["status"] == "running"
                else "paused"
                if job["paused"]
                else "retrying"
                if when and when > now
                else "queued"
            )
        elif any(j["status"] in ("dead", "failed") for j in current):
            state = "failed"
        elif any(
            r.status in ("error", "timeout", "invalid")
            and r.id >= (latest["classify"].id if "classify" in latest else 0)
            for r in latest.values()
        ):
            state = "failed"
        elif latest.get("classify") and latest["classify"].status == "ok":
            state = (
                "needs_review"
                if by_review[doc.id]
                else "categorized"
                if doc.category
                else "completed"
            )
        elif any(r.status == "skipped" for r in latest.values()) or by_review[doc.id]:
            state = "blocked"
        else:
            state = "not_started" if enabled else "disabled"
        suggestion = next(
            (
                i.suggested.get("value")
                for i in by_review[doc.id]
                if i.field == "category" and i.suggested
            ),
            None,
        )
        classify = latest.get("classify")
        items.append(
            {
                "document_id": doc.id,
                "status": state,
                "stage": stage,
                "category": doc.category,
                "category_label": labels.get(doc.category, doc.category),
                "suggested_category": labels.get(suggestion, suggestion) if suggestion else None,
                "ai_run_id": classify.id if classify else None,
            }
        )
    return {"items": items}

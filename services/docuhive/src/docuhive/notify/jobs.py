"""Periodic notification triggers: dead jobs, review backlog, backup age (CL-06 §7.2)."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from docuhive import config, db, jobs
from docuhive.ai import coretables
from docuhive.notify import Notification, send_once
from docuhive.review.models import ReviewItem


@jobs.periodic("notify.scan_dead_jobs", every=timedelta(hours=1))
def scan_dead_jobs(payload: dict, ctx: Any) -> None:
    """New dead jobs, to admins. Read-only use of OA's jobs table (contracts §5)."""
    j = coretables.table("jobs")
    since = datetime.now(UTC) - timedelta(hours=2)  # overlap; send_once dedupes per job id
    with db.session() as s:
        dead = s.execute(
            select(j.c.id, j.c.kind, j.c.last_error).where(
                j.c.status == "dead", j.c.finished_at >= since
            )
        ).all()
    for job_id, kind, error in dead:
        send_once(
            f"job_dead:{job_id}",
            Notification(
                kind="job_dead",
                title=f"A background job failed: {kind}",
                body=f"Job {job_id} ({kind}) gave up: {(error or 'no error text')[:200]}",
                url="/settings/system",
                priority="high",
            ),
            window=timedelta(days=30),
        )


@jobs.periodic("notify.review_backlog", every=timedelta(days=1))
def review_backlog(payload: dict, ctx: Any) -> None:
    threshold = int(config.load_yaml("notify.yaml").get("review_backlog_threshold", 25))
    d = coretables.table("documents")
    with db.session() as s:
        per_owner = s.execute(
            select(d.c.owner_id, func.count())
            .join(ReviewItem, ReviewItem.document_id == d.c.id)
            .where(ReviewItem.status == "pending", d.c.deleted_at.is_(None))
            .group_by(d.c.owner_id)
        ).all()
    for owner, n in per_owner:
        if n > threshold:
            send_once(
                f"review_backlog:{owner}",
                Notification(
                    kind="review_backlog",
                    title=f"{n} AI suggestions are waiting for review",
                    body="Reviewing them keeps your archive tidy and shows DocuHive what is right.",
                    url="/review",
                    priority="low",
                    user_id=owner,
                ),
            )


@jobs.periodic("notify.backup_check", every=timedelta(days=1))
def backup_check(payload: dict, ctx: Any) -> None:
    from docuhive.config.settings import get_settings

    path = get_settings().vault_dir / "_system" / "backup-status.json"
    try:
        status = json.loads(path.read_text())
        at = datetime.fromisoformat(status["at"])
        stale = not status.get("ok") or datetime.now(UTC) - at > timedelta(hours=48)
        detail = status.get("error") or f"last backup {at:%Y-%m-%d %H:%M}"
    except (OSError, KeyError, ValueError):
        stale, detail = True, "no backup status found"
    if stale:
        send_once(
            "backup:stale",
            Notification(
                kind="backup",
                title="No successful backup in the last 48 hours",
                body=f"Check your backup targets ({detail}).",
                url="/settings/system",
                priority="high",
            ),
        )

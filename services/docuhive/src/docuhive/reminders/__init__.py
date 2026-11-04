"""Reminders (QA-05): deadlines from facts with `remind_days_before` in the taxonomy.

Contracts with end_date + notice_period_days also get a derived "Notice deadline"
(end_date - notice_period_days), reminded 30 and 7 days before.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from docuhive import auth, db, documents, fields, taxonomy
from docuhive.ai import coretables
from docuhive.contracts import CurrentUser, DocumentView, Taxonomy
from docuhive.reminders.models import Reminder

NOTICE_DAYS_BEFORE = [30, 7]


def due_dates(view: DocumentView, tax: Taxonomy) -> list[tuple[str, str, date, list[int]]]:
    """(fact, label, due_on, remind_days_before) for one document."""
    dt = fields.document_type(tax, view.document_type)
    if dt is None:
        return []
    out: list[tuple[str, str, date, list[int]]] = []
    for f in dt.facts:
        fact = view.facts.get(f.name)
        if f.type == "date" and f.remind_days_before and fact:
            try:
                out.append(
                    (
                        f.name,
                        f.name.replace("_", " ").capitalize(),
                        date.fromisoformat(fact.value),
                        f.remind_days_before,
                    )
                )
            except ValueError:
                continue
    end, notice = view.facts.get("end_date"), view.facts.get("notice_period_days")
    if end and notice:
        try:
            deadline = date.fromisoformat(end.value) - timedelta(days=int(float(notice.value)))
            out.append(("notice_deadline", "Notice deadline", deadline, NOTICE_DAYS_BEFORE))
        except ValueError:
            pass
    return out


def compute(view: DocumentView, tax: Taxonomy, today: date) -> list[Reminder]:
    return [
        Reminder(
            document_id=view.id,
            fact=fact,
            label=label,
            due_on=due,
            remind_on=due - timedelta(days=n),
            status="scheduled",
        )
        for fact, label, due, days in due_dates(view, tax)
        for n in days
        if due - timedelta(days=n) >= today
    ]  # past reminder dates are not created


def sync(doc_id: str, today: date | None = None) -> int:
    """Recompute: drop scheduled rows that no longer apply, insert the new ones."""
    today = today or date.today()
    view = documents.get(doc_id)
    wanted = {(r.fact, r.remind_on): r for r in compute(view, taxonomy.load(), today)}
    with db.session() as s:
        existing = {
            (r.fact, r.remind_on): r
            for r in s.scalars(select(Reminder).where(Reminder.document_id == doc_id))
        }
        for key, r in existing.items():
            if key not in wanted and r.status == "scheduled":
                s.delete(r)
        for key, r in wanted.items():
            if key not in existing:
                s.add(r)
    return len(wanted)


def scan(today: date | None = None) -> int:
    """Send due reminders to the document owner (only documents still visible to them)."""
    from docuhive.notify import Notification, send

    today = today or date.today()
    d = coretables.table("documents")
    with db.session() as s:
        due = s.execute(
            select(Reminder, d.c.owner_id, d.c.title)
            .join(d, d.c.id == Reminder.document_id)
            .where(
                Reminder.status == "scheduled",
                Reminder.remind_on <= today,
                d.c.deleted_at.is_(None),
            )
        ).all()
        s.expunge_all()
    for r, owner, title in due:
        days = (r.due_on - today).days
        when = "today" if days == 0 else f"in {days} days" if days > 0 else f"{-days} days ago"
        send(
            Notification(
                kind="reminder",
                title=f"{r.label}: {title or 'document'}",
                body=f"{r.label} on {r.due_on.isoformat()} ({when}).",
                url=f"/documents/{r.document_id}",
                user_id=owner,
                priority="high" if days <= 7 else "default",
            )
        )
        with db.session() as s:
            row = s.get_one(Reminder, r.id)
            row.status, row.sent_at = "sent", datetime.now(UTC)
    return len(due)


def upcoming(
    user: CurrentUser, date_from: date | None = None, date_to: date | None = None
) -> list[dict]:
    d = coretables.table("documents")
    q = (
        select(Reminder, d.c.title)
        .join(d, d.c.id == Reminder.document_id)
        .where(auth.visible_docs(user), Reminder.status.in_(("scheduled", "sent")))
        .order_by(Reminder.due_on, Reminder.id)
    )
    if date_from:
        q = q.where(Reminder.due_on >= date_from)
    if date_to:
        q = q.where(Reminder.due_on <= date_to)
    today = date.today()
    seen: dict[tuple[str, str], dict] = {}
    with db.session() as s:
        for r, title in s.execute(q):
            key = (r.document_id, r.fact)  # one row per deadline; earliest pending reminder id
            if key not in seen:
                seen[key] = {
                    "id": r.id,
                    "document_id": r.document_id,
                    "title": title,
                    "fact": r.fact,
                    "label": r.label,
                    "due_on": r.due_on,
                    "remind_on": r.remind_on,
                    "status": r.status,
                    "days_left": (r.due_on - today).days,
                }
    return list(seen.values())


def resolve(reminder_id: int, user: CurrentUser, status: str) -> None:
    """Dismiss / done applies to the whole deadline (all reminder dates for that fact)."""
    with db.session() as s:
        r = s.get(Reminder, reminder_id)
        if r is None:
            raise LookupError("not found")
        doc_id, fact = r.document_id, r.fact
    view = documents.get_for_user(doc_id, user)
    if view.owner_id != user.id:
        raise PermissionError("Only the document owner can change its reminders")
    with db.session() as s:
        for row in s.scalars(
            select(Reminder).where(Reminder.document_id == doc_id, Reminder.fact == fact)
        ):
            row.status = status


def ics(items: list[dict]) -> str:
    """A hand-written iCalendar feed: one all-day event per deadline."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DocuHive//Reminders//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:DocuHive deadlines",
    ]
    for it in items:
        due: date = it["due_on"]
        summary = f"{it['label']}: {it['title'] or 'document'}".replace(",", "\\,").replace(
            ";", "\\;"
        )
        lines += [
            "BEGIN:VEVENT",
            f"UID:docuhive-{it['document_id']}-{it['fact']}@docuhive",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{due:%Y%m%d}",
            f"DTEND;VALUE=DATE:{due + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{summary}",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{summary}",
            "TRIGGER:-P7D",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

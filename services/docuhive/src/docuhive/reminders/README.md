# `services/docuhive/src/docuhive/reminders`

**Overview.** Reminders built from extracted dates (due dates, renewals, notice deadlines), plus an iCalendar feed.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Reminders: deadlines from facts with `remind_days_before` in the taxonomy |
| [`jobs.py`](jobs.py) | reminders.sync {document_id} and the periodic reminders.scan (sent from 07:00 local time) |
| [`models.py`](models.py) | reminders: one row per (document, fact, remind_on) |
| [`routes.py`](routes.py) | /api/reminders: upcoming deadlines, dismiss/done, and an iCalendar feed |

## Extending

When to remind is configured per fact in the taxonomy (`remind_days_before`).

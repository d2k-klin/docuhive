"""Deadlines that belong to a person rather than a document (a tax return, a notice date)."""

from datetime import date

from ._plugin import current


def set(
    owner_id: int, key: str, label: str, due_on: date, *, days_before: list[int], link: str
) -> None:  # noqa: A001
    """Remind `owner_id` before `due_on`; shown under Reminders and in the calendar feed.
    `key` identifies the deadline within your plugin: setting it again replaces it."""
    from docuhive import reminders

    registry = current()
    reminders.set_owned(owner_id, f"plugin:{registry.id}:{key}", label, due_on, days_before, link)


def clear(owner_id: int, key: str) -> None:
    from docuhive import reminders

    reminders.clear_owned(owner_id, f"plugin:{current().id}:{key}")

"""Shared touchpoint: append handler modules; preserve other track registrations."""

HANDLER_MODULES: list[str] = []

# OA: platform jobs
HANDLER_MODULES += [
    "docuhive.vault.health",
    "docuhive.vault.meta",
    "docuhive.ingest.process",
    "docuhive.duplicates",
]

# CL: AI pipeline, index, mail, reminders, notifications, analyses (see docuhive/ai/startup.py)
HANDLER_MODULES += [
    "docuhive.agents.pipeline",
    "docuhive.index.jobs",
    "docuhive.mail.jobs",
    "docuhive.reminders.jobs",
    "docuhive.notify.jobs",
    "docuhive.chat.jobs",
]

HANDLER_MODULES += ["docuhive.ingest.consume", "docuhive.vault.library"]

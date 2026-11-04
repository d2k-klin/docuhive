"""docuhive.ai.startup(): called once by the API and the worker (safe to call twice)."""

import logging
from importlib import import_module

from docuhive import search, taxonomy
from docuhive.ai import routing
from docuhive.ai.settings import get_ai_settings

log = logging.getLogger(__name__)

# Modules whose @jobs.handler / @jobs.periodic decorators register CL jobs on import.
HANDLER_MODULES = [
    "docuhive.agents.pipeline",
    "docuhive.index.jobs",
    "docuhive.mail.jobs",
    "docuhive.reminders.jobs",
    "docuhive.notify.jobs",
    "docuhive.chat.jobs",
]


def startup() -> None:
    routing.load()  # fail fast on an invalid routing.yaml / taxonomy.yaml (errors name the path)
    taxonomy.load()
    for name in HANDLER_MODULES:
        import_module(name)
    if get_ai_settings().enabled:
        from docuhive.index.semantic import semantic_chunks, semantic_search

        search.register_semantic(semantic_search)
        search.register_chunk_semantic(semantic_chunks)
    else:
        log.info("AI disabled: AI jobs will be skipped with the note 'AI disabled'")

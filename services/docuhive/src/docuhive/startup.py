"""Optional intelligence extension initialization."""

import logging
from importlib import import_module

log = logging.getLogger(__name__)


def start_intelligence() -> None:
    try:
        module = import_module("docuhive.ai")
        startup = getattr(module, "startup", None)
        if startup is not None:
            startup()
    except ImportError:
        # Core-only installs and a track still being bootstrapped remain runnable.
        log.warning("Optional intelligence extensions are unavailable; their jobs will wait")

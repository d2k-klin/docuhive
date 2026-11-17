"""The one package plugins import. Stable within a major version (see version.py)."""

from docuhive import retention
from docuhive.contracts import CurrentUser as User
from docuhive.contracts import DocumentView, FactValue

from . import ai, documents, guest_links, http, mail, profiles, reminders, render, services, users
from .pages import ActionError, Result
from .registry import CapabilityMissing, Registry
from .version import __version__

__all__ = [
    "ActionError",
    "CapabilityMissing",
    "DocumentView",
    "FactValue",
    "Registry",
    "Result",
    "User",
    "__version__",
    "ai",
    "documents",
    "guest_links",
    "http",
    "mail",
    "profiles",
    "reminders",
    "render",
    "retention",
    "services",
    "users",
]

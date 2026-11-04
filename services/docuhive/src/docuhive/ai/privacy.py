"""Privacy gate (AI-03): restricted documents are only ever sent to local models."""

from docuhive.ai import routing
from docuhive.contracts import DocumentView, Taxonomy


class NoAllowedRoute(Exception):
    """Every route for the task was filtered out (privacy) or is disabled."""

    def __init__(self, task: str, reason: str):
        super().__init__(f"{task}: {reason}")
        self.task, self.reason = task, reason


def restricted_category(category: str | None, taxonomy: Taxonomy) -> bool:
    """'health' restricted => 'health/medical' restricted too."""
    if not category:
        return False
    restricted = {c.id for c in taxonomy.categories if c.restricted}
    parts = category.split("/")
    return any("/".join(parts[:i]) in restricted for i in range(1, len(parts) + 1))


def is_restricted(doc: DocumentView | None, taxonomy: Taxonomy) -> bool:
    p = routing.load().privacy
    if p.local_only:
        return True
    if doc is None:
        return False
    return restricted_category(doc.category, taxonomy) or bool(
        set(doc.tags) & set(p.restricted_tags)
    )


def must_stay_local(task: str, doc: DocumentView | None, taxonomy: Taxonomy) -> bool:
    """is_restricted, plus: an unclassified document is classified locally first, because its
    category (and so its privacy level) is unknown until then."""
    if is_restricted(doc, taxonomy):
        return True
    p = routing.load().privacy
    return (
        task == "classify" and p.classify_unknown_locally and doc is not None and not doc.category
    )

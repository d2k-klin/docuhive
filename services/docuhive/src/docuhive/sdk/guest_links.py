"""Read-only links for someone without an account, such as a tax advisor. Only from a page action
a person pressed; at most 30 days; the person sees and copies the link."""

from datetime import datetime

from docuhive import guest_links as core
from docuhive.contracts import CurrentUser

from ._plugin import current, require_interactive
from .pages import ActionError


class PrivateDocuments(ActionError):
    """Some documents are private: ask the person, then call again with include_private=True."""

    def __init__(self, ids: list[str]) -> None:
        super().__init__("Some of these documents are private. Confirm to share them too.")
        self.ids = ids


def create(
    user: CurrentUser,
    label: str,
    document_ids: list[str],
    days: int = 7,
    *,
    include_private: bool = False,
) -> dict:
    """{"path": "/guest/<token>", "expires_at": …}. The path is shown once; keep nothing of it."""
    current()
    require_interactive()
    try:
        link, token = core.create(user, label, document_ids, days, include_private=include_private)
    except core.Disabled as error:
        raise ActionError("Guest links are switched off on this installation.") from error
    except core.NeedsConfirmation as error:
        raise PrivateDocuments(error.ids) from error
    expires: datetime = link.expires_at
    return {"id": link.id, "path": f"/guest/{token}", "expires_at": expires}

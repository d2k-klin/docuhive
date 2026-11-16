"""Send mail as one of the person's identities. Only from a page action the person pressed, with
`mail:send` in plugin.yaml; the page asks them to confirm first (an `outgoing` action)."""

from docuhive import outgoing
from docuhive.contracts import CurrentUser

from ._plugin import current, require_interactive
from .pages import ActionError


def send(
    user: CurrentUser,
    profile_id: int,
    to: list[str],
    subject: str,
    body_text: str,
    attachments: list[str] = (),  # type: ignore[assignment]
    *,
    reply_to: str | None = None,
) -> dict:
    """{"document_id": the stored mail, "recipients": [...]}. Attachments are document ids; their
    PDFs are attached, and they are locked as sent."""
    registry = current()
    registry.require("mail:send")
    require_interactive()
    try:
        sent = outgoing.send(
            user,
            profile_id,
            to,
            subject,
            body_text,
            list(attachments),
            reply_to=reply_to,
            generator=registry.id,
        )
    except outgoing.Refused as error:
        raise ActionError(str(error)) from error
    return {"document_id": sent.document_id, "recipients": sent.recipients}

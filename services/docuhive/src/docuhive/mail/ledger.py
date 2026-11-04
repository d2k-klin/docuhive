"""Keep mail_attachments in step with OA's document events."""

from sqlalchemy import update

from docuhive import db
from docuhive.mail.models import MailAttachment


def on_document(doc_id: str, status: str, reason: str | None = None) -> None:
    """document.stored / document.quarantined -> attachment status (no-op for non-mail docs)."""
    with db.session() as s:
        s.execute(
            update(MailAttachment)
            .where(MailAttachment.document_id == doc_id, MailAttachment.status == "submitted")
            .values(status=status, reason=reason)
        )

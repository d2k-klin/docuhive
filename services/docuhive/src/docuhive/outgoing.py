"""Sending mail as one of your identities, when a person asks for it.

What was sent is kept: the message is stored as an `.eml` document linked to its attachments,
both are locked, and each attachment's history says to whom it went. If the server refuses,
nothing is stored as sent and the person sees the server's reason in plain words.
"""

import re
import smtplib
import tempfile
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from docuhive import db, profiles
from docuhive import documents as core
from docuhive.contracts import CurrentUser, MetadataPatch
from docuhive.db.models import AuditLog

MAX_RECIPIENTS = 20
PER_HOUR = 50  # per identity
ADDRESS = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


class Refused(ValueError):
    """Not sent; the message is for people."""


@dataclass
class Sent:
    document_id: str  # the stored .eml
    recipients: list[str]


class _Limiter:
    # ponytail: per process, like the login limiter; a DB count when the API runs replicas.
    def __init__(self) -> None:
        self.sent: dict[int, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def take(self, profile_id: int, n: int) -> bool:
        with self.lock:
            now, times = time.monotonic(), self.sent[profile_id]
            while times and times[0] <= now - 3600:
                times.popleft()
            if len(times) + n > PER_HOUR:
                return False
            times.extend([now] * n)
            return True


limiter = _Limiter()


def _archive_pdf(doc_id: str) -> tuple[str, bytes]:
    from sqlalchemy import select

    from docuhive import vault
    from docuhive.db.models import Document

    view = core.get(doc_id)
    with db.session() as s:
        vault_path = s.scalar(select(Document.vault_path).where(Document.id == doc_id))
    root = vault.root().resolve()
    path = (root / vault_path / "archive.pdf").resolve() if vault_path else None
    if path is None or not path.is_relative_to(root) or not path.is_file():
        raise Refused(f"“{view.title or 'A document'}” has no PDF yet; try again once it is read.")
    name = Path(view.source.original_filename or view.title or "document").stem or "document"
    return f"{name}.pdf", path.read_bytes()


def send(
    user: CurrentUser,
    profile_id: int,
    to: list[str],
    subject: str,
    body: str,
    attachments: list[str] = (),  # type: ignore[assignment]
    *,
    reply_to: str | None = None,
    generator: str | None = None,
    copy_to_sender: bool = True,
    keep: bool = True,  # False only for the settings page's test mail
) -> Sent:
    from docuhive import ingest
    from docuhive.contracts import IngestRequest, SourceInfo, SourceKind
    from docuhive.documents import holds

    recipients = [a.strip() for a in to if a and a.strip()]
    if not recipients or len(recipients) > MAX_RECIPIENTS:
        raise Refused(f"Send to between 1 and {MAX_RECIPIENTS} addresses.")
    if bad := [a for a in recipients + ([reply_to] if reply_to else []) if not ADDRESS.match(a)]:
        raise Refused(f"Not a mail address: {', '.join(bad)}")
    if not subject.strip():
        raise Refused("The mail needs a subject.")
    try:
        identity = profiles.get(user, profile_id)
    except profiles.NotFound as error:
        raise Refused("Choose one of your identities to send from.") from error
    if identity.smtp is None:
        raise Refused(f"“{identity.name}” has no mail server set up (Settings → Identities).")
    files = [_archive_pdf(core.get_for_user(d, user).id) for d in dict.fromkeys(attachments)]
    if not limiter.take(profile_id, len(recipients)):
        raise Refused(f"At most {PER_HOUR} mails an hour from one identity. Try again later.")

    msg = EmailMessage()
    msg["From"] = formataddr((identity.name, identity.smtp.from_address))
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject.strip()
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=identity.smtp.from_address.split("@")[-1])
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    for name, data in files:
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=name)
    envelope = recipients + ([identity.smtp.from_address] if copy_to_sender else [])
    host, port = identity.smtp.host, int(identity.smtp.port)
    try:
        client = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        with client(host, port, timeout=30) as smtp:
            if port != 465:
                smtp.ehlo()
                if smtp.has_extn("starttls"):
                    smtp.starttls()
                    smtp.ehlo()
                elif identity.smtp.username:  # never a password over a plain connection
                    raise Refused("The mail server offers no encryption; the mail was not sent.")
            if identity.smtp.username:
                smtp.login(identity.smtp.username, profiles.smtp_password(profile_id) or "")
            smtp.send_message(msg, to_addrs=envelope)  # Bcc: the copy is not in the headers
    except smtplib.SMTPAuthenticationError as error:
        raise Refused("The mail server did not accept the user name or password.") from error
    except (smtplib.SMTPException, OSError) as error:
        raise Refused(
            f"The mail server could not be reached or refused the mail: {error}"
        ) from error

    if not keep:
        return Sent(document_id="", recipients=recipients)
    # Sent: keep it, lock it, and say so on every attachment.
    folder = Path(tempfile.mkdtemp(dir=ingest.incoming_dir()))
    path = folder / "sent.eml"
    path.write_bytes(bytes(msg))
    sources = list(dict.fromkeys(attachments))
    try:
        result = ingest.submit(
            [path],
            IngestRequest(
                owner_id=user.id,
                shared=False,
                source=SourceInfo(
                    kind=SourceKind.plugin if generator else SourceKind.upload,
                    original_filename="sent.eml",
                    generator=generator,
                    derived_from=sources,
                    email_from=identity.smtp.from_address,
                    subject=subject.strip()[:300],
                ),
                hints={"skip_ai": "1", **({"plugin": generator} if generator else {})},
            ),
        )
    finally:
        path.unlink(missing_ok=True)
        folder.rmdir()
    if result.status == "staged":
        core.apply_metadata(
            result.document_id,
            MetadataPatch(title=f"Sent: {subject.strip()}"[:200], tags_add=["sent"]),
            actor=f"user:{user.id}",
        )
    reason = f"Sent by mail to {', '.join(recipients)}"[:300]
    with db.session() as s:
        for doc_id in [result.document_id, *sources]:
            holds.place(s, doc_id, reason, placed_by=f"user:{user.id}")
            s.add(
                AuditLog(
                    actor=f"user:{user.id}",
                    document_id=doc_id,
                    action="sent",
                    after={"to": recipients, "subject": subject.strip(), "from": identity.name},
                )
            )
    return Sent(document_id=result.document_id, recipients=recipients)

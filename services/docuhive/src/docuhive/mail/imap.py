"""IMAP connector (stdlib imaplib + email). BODY.PEEK so messages are never marked read."""

import email
import email.policy
import imaplib
from collections.abc import Callable
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from docuhive.mail.base import AttachmentMeta, MailMessage, MsgRef, snippet, strip_html


def parse(
    raw: bytes, ref: MsgRef, labels: list[str] | None = None
) -> tuple[MailMessage, list[EmailMessage]]:
    """Parse an RFC 822 message. Attachment ids are their index in the walk order."""
    msg: EmailMessage = email.message_from_bytes(raw, policy=email.policy.default)  # type: ignore[assignment]
    parts = list(msg.walk())
    atts = []
    for i, part in enumerate(parts):
        name = part.get_filename()
        if name and not part.is_multipart():
            payload = part.get_payload(decode=True) or b""
            inline = (part.get_content_disposition() == "inline") and bool(part.get("Content-ID"))
            atts.append(
                AttachmentMeta(
                    provider_att_id=str(i),
                    filename=name,
                    mime=part.get_content_type(),
                    size=len(payload),
                    inline=inline,
                )
            )
    plain = msg.get_body(("plain",))
    html = msg.get_body(("html",))
    text = plain.get_content() if plain else strip_html(html.get_content()) if html else ""
    try:
        received = parsedate_to_datetime(msg["Date"]) if msg["Date"] else ref.received_at
    except (TypeError, ValueError):
        received = ref.received_at
    headers = {k: str(v) for k, v in msg.items()}
    return MailMessage(
        ref=MsgRef(ref.provider_msg_id, received),
        rfc_message_id=msg["Message-ID"],
        email_from=str(msg["From"] or ""),
        to=[str(msg["To"] or "")],
        subject=str(msg["Subject"] or ""),
        headers=headers,
        labels=labels or [],
        text_snippet=snippet(text),
        has_html_body=html is not None,
        attachments=atts,
    ), parts


def _imap_date(d: datetime) -> str:
    return d.strftime("%d-%b-%Y")


class Imap:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        *,
        ssl: bool = True,
        folders: list[str] | None = None,
        factory: Callable | None = None,
    ):
        self.host, self.port, self.username, self.password = host, port, username, password
        self.folders = folders or ["INBOX"]
        self.factory = factory or (
            lambda h, p: (imaplib.IMAP4_SSL if ssl else imaplib.IMAP4)(h, p, timeout=20)
        )
        self._conn: Any = None

    def conn(self):  # type: ignore[no-untyped-def]
        if self._conn is None:
            self._conn = self.factory(self.host, self.port)
            self._conn.login(self.username, self.password)
        return self._conn

    def _select(self, folder: str) -> str:
        c = self.conn()
        c.select(f'"{folder}"', readonly=True)
        _, data = c.response("UIDVALIDITY")
        return data[0].decode() if data and data[0] else "0"

    def list_range(
        self, since: datetime, until: datetime, page_token: str | None, page_size: int = 100
    ) -> tuple[list[MsgRef], str | None]:
        fi, offset = (int(x) for x in (page_token or "0:0").split(":"))
        if fi >= len(self.folders):
            return [], None
        folder = self.folders[fi]
        validity = self._select(folder)
        # IMAP dates are whole days: BEFORE is exclusive, so add a day to include `until`.
        _, data = self.conn().uid(
            "SEARCH",
            None,
            "SINCE",
            _imap_date(since),
            "BEFORE",
            _imap_date(until + timedelta(days=1)),
        )
        uids = data[0].split() if data and data[0] else []
        page = uids[offset : offset + page_size]
        refs = [MsgRef(f"{folder}:{validity}:{u.decode()}", since) for u in page]
        if offset + page_size < len(uids):
            nxt: str | None = f"{fi}:{offset + page_size}"
        else:
            nxt = f"{fi + 1}:0" if fi + 1 < len(self.folders) else None
        return refs, nxt

    def _fetch(self, ref: MsgRef) -> bytes:
        folder, validity, uid = ref.provider_msg_id.rsplit(":", 2)
        if self._select(folder) != validity:
            raise LookupError(f"UIDVALIDITY of {folder} changed; message ids are stale")
        _, data = self.conn().uid("FETCH", uid, "(BODY.PEEK[])")
        for item in data:
            if isinstance(item, tuple):
                return item[1]
        raise LookupError(f"message {uid} not found in {folder}")

    def get_message(self, ref: MsgRef) -> MailMessage:
        folder = ref.provider_msg_id.rsplit(":", 2)[0]
        return parse(self._fetch(ref), ref, [folder])[0]

    def download_attachment(self, ref: MsgRef, att: AttachmentMeta, dest: Path) -> None:
        parts = parse(self._fetch(ref), ref)[1]
        payload = parts[int(att.provider_att_id or 0)].get_payload(decode=True)
        dest.write_bytes(payload if isinstance(payload, bytes) else b"")

    def download_raw(self, ref: MsgRef, dest: Path) -> None:
        dest.write_bytes(self._fetch(ref))

    def mark_imported(self, ref: MsgRef) -> None:
        pass  # IMAP keywords are optional (backlog)

    def test_login(self) -> None:
        self.conn()
        for f in self.folders:
            typ, _ = self._conn.select(f'"{f}"', readonly=True)  # type: ignore[union-attr]
            if typ != "OK":
                raise LookupError(f"folder {f!r} not found")

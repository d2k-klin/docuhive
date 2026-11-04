"""The connector interface. Three implementations (Gmail, Graph, IMAP) justify a small Protocol."""

from datetime import datetime
from pathlib import Path
from typing import NamedTuple, Protocol

from pydantic import BaseModel


class MsgRef(NamedTuple):
    provider_msg_id: str
    received_at: datetime


class AttachmentMeta(BaseModel):
    provider_att_id: str | None
    filename: str
    mime: str | None = None
    size: int | None = None
    inline: bool = False
    kind: str = "file"  # graph: fileAttachment | itemAttachment | referenceAttachment


class MailMessage(BaseModel):
    ref: MsgRef
    rfc_message_id: str | None = None
    email_from: str = ""
    to: list[str] = []
    subject: str = ""
    headers: dict[str, str] = {}  # List-Unsubscribe, Precedence, Auto-Submitted, ...
    labels: list[str] = []  # Gmail labels, Graph categories/folder, IMAP folder
    text_snippet: str = ""  # first 2 KB of the text body (HTML stripped)
    has_html_body: bool = False
    attachments: list[AttachmentMeta] = []


class NeedsReauth(Exception):
    """The refresh token was rejected (invalid_grant): the user must reconnect."""


class RateLimited(Exception):
    def __init__(self, retry_after_s: float):
        super().__init__(f"rate limited, retry after {retry_after_s:.0f}s")
        self.retry_after_s = retry_after_s


class Connector(Protocol):
    def list_range(
        self, since: datetime, until: datetime, page_token: str | None, page_size: int = 100
    ) -> tuple[list[MsgRef], str | None]: ...
    def get_message(self, ref: MsgRef) -> MailMessage: ...
    def download_attachment(self, ref: MsgRef, att: AttachmentMeta, dest: Path) -> None: ...
    def download_raw(self, ref: MsgRef, dest: Path) -> None: ...
    def mark_imported(self, ref: MsgRef) -> None: ...


def strip_html(html: str) -> str:
    import re
    from html import unescape

    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return " ".join(unescape(text).split())


def snippet(text: str, limit: int = 2048) -> str:
    return " ".join(text.split())[:limit]

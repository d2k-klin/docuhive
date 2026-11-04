"""Gmail REST connector (httpx). Read-only unless label_on_import is on."""

import base64
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from docuhive.mail.base import AttachmentMeta, MailMessage, MsgRef, RateLimited, snippet, strip_html

BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
IMPORTED_LABEL = "DocuHive/Imported"


def _b64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class Gmail:
    def __init__(
        self,
        token: Callable[[], str],
        client: httpx.Client | None = None,
        label_on_import: bool = False,
    ):
        self.token, self.http = token, client or httpx.Client(timeout=60)
        self.label_on_import = label_on_import
        self._label_id: str | None = None

    def _req(self, method: str, path: str, **kw) -> httpx.Response:  # type: ignore[no-untyped-def]
        r = self.http.request(
            method, f"{BASE}/{path}", headers={"Authorization": f"Bearer {self.token()}"}, **kw
        )
        if r.status_code == 429 or (r.status_code == 403 and "rateLimitExceeded" in r.text):
            raise RateLimited(float(r.headers.get("Retry-After", 10)))
        r.raise_for_status()
        return r

    def list_range(
        self, since: datetime, until: datetime, page_token: str | None, page_size: int = 100
    ) -> tuple[list[MsgRef], str | None]:
        params = {
            "q": f"after:{int(since.timestamp())} before:{int(until.timestamp())} -in:chats",
            "maxResults": page_size,
        }
        if page_token:
            params["pageToken"] = page_token
        body = self._req("GET", "messages", params=params).json()
        # ponytail: the list call carries no dates; the window start stands in until
        # mail.process reads internalDate (saves one API call per message).
        refs = [MsgRef(m["id"], since) for m in body.get("messages", [])]
        return refs, body.get("nextPageToken")

    def get_message(self, ref: MsgRef) -> MailMessage:
        m = self._req("GET", f"messages/{ref.provider_msg_id}", params={"format": "full"}).json()
        payload = m.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        atts: list[AttachmentMeta] = []
        texts: dict[str, str] = {}

        def walk(part: dict) -> None:
            body, mime = part.get("body", {}), part.get("mimeType", "")
            ph = {h["name"].lower(): h["value"] for h in part.get("headers", [])}
            if part.get("filename") and body.get("attachmentId"):
                inline = (
                    ph.get("content-disposition", "").startswith("inline") and "content-id" in ph
                )
                atts.append(
                    AttachmentMeta(
                        provider_att_id=body["attachmentId"],
                        filename=part["filename"],
                        mime=mime,
                        size=body.get("size"),
                        inline=inline,
                    )
                )
            elif mime in ("text/plain", "text/html") and body.get("data"):
                texts.setdefault(mime, _b64(body["data"]).decode("utf-8", "replace"))
            for p in part.get("parts", []):
                walk(p)

        walk(payload)
        text = texts.get("text/plain") or strip_html(texts.get("text/html", ""))
        received = datetime.fromtimestamp(int(m.get("internalDate", 0)) / 1000, UTC)
        return MailMessage(
            ref=MsgRef(ref.provider_msg_id, received),
            rfc_message_id=headers.get("Message-ID"),
            email_from=headers.get("From", ""),
            to=[headers.get("To", "")],
            subject=headers.get("Subject", ""),
            headers=headers,
            labels=m.get("labelIds", []),
            text_snippet=snippet(text),
            has_html_body="text/html" in texts,
            attachments=atts,
        )

    def download_attachment(self, ref: MsgRef, att: AttachmentMeta, dest: Path) -> None:
        data = self._req(
            "GET", f"messages/{ref.provider_msg_id}/attachments/{att.provider_att_id}"
        ).json()["data"]
        dest.write_bytes(_b64(data))

    def download_raw(self, ref: MsgRef, dest: Path) -> None:
        raw = self._req("GET", f"messages/{ref.provider_msg_id}", params={"format": "raw"})
        dest.write_bytes(_b64(raw.json()["raw"]))

    def mark_imported(self, ref: MsgRef) -> None:
        if not self.label_on_import:
            return
        if self._label_id is None:
            labels = self._req("GET", "labels").json().get("labels", [])
            found = next((lb["id"] for lb in labels if lb["name"] == IMPORTED_LABEL), None)
            self._label_id = (
                found
                or self._req(
                    "POST",
                    "labels",
                    json={
                        "name": IMPORTED_LABEL,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                    },
                ).json()["id"]
            )
        self._req(
            "POST", f"messages/{ref.provider_msg_id}/modify", json={"addLabelIds": [self._label_id]}
        )

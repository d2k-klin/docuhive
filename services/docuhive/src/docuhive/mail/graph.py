"""Microsoft Graph connector (Outlook.com / Live / Microsoft 365), httpx."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from docuhive.mail.base import AttachmentMeta, MailMessage, MsgRef, RateLimited, snippet, strip_html

BASE = "https://graph.microsoft.com/v1.0/me"
CATEGORY = "DocuHive Imported"
SKIP_FOLDERS = ("deleteditems", "junkemail")


def _iso(d: datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class Graph:
    def __init__(
        self,
        token: Callable[[], str],
        client: httpx.Client | None = None,
        label_on_import: bool = False,
    ):
        self.token, self.http = token, client or httpx.Client(timeout=60)
        self.label_on_import = label_on_import
        self._skip: set[str] | None = None

    def _req(self, method: str, url: str, **kw) -> httpx.Response:  # type: ignore[no-untyped-def]
        if not url.startswith("https://"):
            url = f"{BASE}/{url}"
        r = self.http.request(
            method, url, headers={"Authorization": f"Bearer {self.token()}"}, **kw
        )
        if r.status_code in (429, 503) and "Retry-After" in r.headers:
            raise RateLimited(float(r.headers["Retry-After"]))
        r.raise_for_status()
        return r

    def _skip_folders(self) -> set[str]:
        if self._skip is None:
            self._skip = {
                self._req("GET", f"mailFolders/{f}", params={"$select": "id"}).json()["id"]
                for f in SKIP_FOLDERS
            }
        return self._skip

    def list_range(
        self, since: datetime, until: datetime, page_token: str | None, page_size: int = 100
    ) -> tuple[list[MsgRef], str | None]:
        if page_token:  # the @odata.nextLink of the previous page
            body = self._req("GET", page_token).json()
        else:
            body = self._req(
                "GET",
                "messages",
                params={
                    "$filter": f"receivedDateTime ge {_iso(since)} "
                    f"and receivedDateTime lt {_iso(until)}",
                    "$select": "id,receivedDateTime,parentFolderId",
                    "$orderby": "receivedDateTime",
                    "$top": page_size,
                },
            ).json()
        skip = self._skip_folders()
        refs = [
            MsgRef(m["id"], _dt(m["receivedDateTime"]))
            for m in body.get("value", [])
            if m.get("parentFolderId") not in skip
        ]
        return refs, body.get("@odata.nextLink")

    def get_message(self, ref: MsgRef) -> MailMessage:
        m = self._req(
            "GET",
            f"messages/{ref.provider_msg_id}",
            params={
                "$select": (
                    "id,internetMessageId,receivedDateTime,from,toRecipients,subject,"
                    "internetMessageHeaders,categories,body,hasAttachments"
                )
            },
        ).json()
        atts: list[AttachmentMeta] = []
        if m.get("hasAttachments"):
            for a in (
                self._req(
                    "GET",
                    f"messages/{ref.provider_msg_id}/attachments",
                    params={"$select": "id,name,contentType,size,isInline"},
                )
                .json()
                .get("value", [])
            ):
                kind = a.get("@odata.type", "#microsoft.graph.fileAttachment").rsplit(".", 1)[-1]
                atts.append(
                    AttachmentMeta(
                        provider_att_id=a["id"],
                        filename=a.get("name") or "",
                        mime=a.get("contentType"),
                        size=a.get("size"),
                        inline=bool(a.get("isInline")),
                        kind=kind,
                    )
                )
        body = m.get("body", {})
        html = body.get("contentType") == "html"
        text = strip_html(body.get("content", "")) if html else body.get("content", "")
        headers = {h["name"]: h["value"] for h in m.get("internetMessageHeaders") or []}
        sender = (m.get("from") or {}).get("emailAddress", {})
        return MailMessage(
            ref=MsgRef(ref.provider_msg_id, _dt(m["receivedDateTime"])),
            rfc_message_id=m.get("internetMessageId"),
            email_from=sender.get("address", ""),
            to=[r["emailAddress"]["address"] for r in m.get("toRecipients", [])],
            subject=m.get("subject") or "",
            headers=headers,
            labels=m.get("categories", []),
            text_snippet=snippet(text),
            has_html_body=html,
            attachments=atts,
        )

    def download_attachment(self, ref: MsgRef, att: AttachmentMeta, dest: Path) -> None:
        r = self._req(
            "GET", f"messages/{ref.provider_msg_id}/attachments/{att.provider_att_id}/$value"
        )
        dest.write_bytes(r.content)

    def download_raw(self, ref: MsgRef, dest: Path) -> None:
        dest.write_bytes(self._req("GET", f"messages/{ref.provider_msg_id}/$value").content)

    def mark_imported(self, ref: MsgRef) -> None:
        if not self.label_on_import:
            return
        cats = (
            self._req("GET", f"messages/{ref.provider_msg_id}", params={"$select": "categories"})
            .json()
            .get("categories", [])
        )
        if CATEGORY not in cats:
            self._req(
                "PATCH", f"messages/{ref.provider_msg_id}", json={"categories": [*cats, CATEGORY]}
            )

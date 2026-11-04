"""Deterministic mail rules (mail-rules.yaml) before the triage agent: skip | triage | import."""

from email.utils import parseaddr
from fnmatch import fnmatch
from typing import Literal

from pydantic import BaseModel

from docuhive import config
from docuhive.mail.base import AttachmentMeta, MailMessage


class Rules(BaseModel):
    attachment_mime_allow: list[str] = []
    min_attachment_kb: int = 15
    skip_inline_images: bool = True
    skip_labels: list[str] = []
    skip_if_list_unsubscribe_and_no_attachment: bool = True
    skip_auto_submitted: bool = False
    deny_senders: list[str] = []
    allow_senders: list[str] = []
    body_archive_senders: list[str] = []


class PrefilterResult(BaseModel):
    decision: Literal["skip", "triage", "import"]
    reason: str
    candidate_attachments: list[AttachmentMeta] = []
    archive_body: bool = False


def rules_for(address: str) -> Rules:
    raw = config.load_yaml("mail-rules.yaml")
    merged = {**raw.get("defaults", {}), **(raw.get("accounts") or {}).get(address.lower(), {})}
    return Rules(**merged)


def sender(m: MailMessage) -> str:
    return parseaddr(m.email_from)[1].lower()


def _match(addr: str, patterns: list[str]) -> bool:
    return any(fnmatch(addr, p.lower()) for p in patterns)


def candidates(m: MailMessage, r: Rules) -> list[AttachmentMeta]:
    out = []
    for a in m.attachments:
        mime = (a.mime or "").lower()
        if a.kind == "itemAttachment" or mime not in r.attachment_mime_allow:
            continue
        if a.size is not None and a.size < r.min_attachment_kb * 1024:
            continue
        if r.skip_inline_images and a.inline and mime.startswith("image/"):
            continue
        out.append(a)
    return out


def prefilter(m: MailMessage, r: Rules) -> PrefilterResult:
    addr = sender(m)
    cands = candidates(m, r)
    archive_body = _match(addr, r.body_archive_senders)
    if _match(addr, r.deny_senders):
        return PrefilterResult(decision="skip", reason="prefilter:deny_sender")
    if _match(addr, r.allow_senders):
        return PrefilterResult(
            decision="import",
            reason="prefilter:allow_sender",
            candidate_attachments=cands,
            archive_body=archive_body,
        )
    if hit := next((lb for lb in m.labels if lb in r.skip_labels), None):
        return PrefilterResult(
            decision="skip", reason=f"prefilter:{hit.removeprefix('CATEGORY_').lower()}"
        )
    if r.skip_auto_submitted and m.headers.get("Auto-Submitted", "no").lower() != "no":
        return PrefilterResult(decision="skip", reason="prefilter:auto_submitted")
    if (
        not cands
        and r.skip_if_list_unsubscribe_and_no_attachment
        and any(k.lower() == "list-unsubscribe" for k in m.headers)
    ):
        return PrefilterResult(decision="skip", reason="prefilter:newsletter")
    if not cands and not archive_body:
        return PrefilterResult(decision="skip", reason="prefilter:no_attachment")
    return PrefilterResult(
        decision="triage",
        reason="prefilter:candidate",
        candidate_attachments=cands,
        archive_body=archive_body,
    )

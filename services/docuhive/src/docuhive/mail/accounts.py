"""Credentials at rest and the connector for an account."""

import json

from docuhive.mail.base import Connector
from docuhive.mail.models import MailAccount
from docuhive.mail.settings import fernet


def encrypt(creds: dict) -> bytes:
    return fernet().encrypt(json.dumps(creds).encode())


def credentials(acc: MailAccount) -> dict:
    return json.loads(fernet().decrypt(acc.enc_credentials))


def connector_for(acc: MailAccount) -> Connector:
    from docuhive.mail import oauth

    if acc.provider == "gmail":
        from docuhive.mail.gmail import Gmail

        return Gmail(lambda: oauth.access_token(acc.id), label_on_import=acc.label_on_import)
    if acc.provider == "graph":
        from docuhive.mail.graph import Graph

        return Graph(lambda: oauth.access_token(acc.id), label_on_import=acc.label_on_import)
    from docuhive.mail.imap import Imap

    c = credentials(acc)
    return Imap(
        c["host"],
        int(c.get("port", 993)),
        c["username"],
        c["password"],
        ssl=c.get("ssl", True),
        folders=c.get("folders") or ["INBOX"],
    )

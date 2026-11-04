# `services/docuhive/src/docuhive/mail`

**Overview.** Email intake: Gmail, Microsoft Graph and IMAP connectors, sign-in, deterministic rules, sync and backfill.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Package marker |
| [`accounts.py`](accounts.py) | Credentials at rest and the connector for an account |
| [`base.py`](base.py) | The connector interface |
| [`gmail.py`](gmail.py) | Gmail REST connector (httpx) |
| [`graph.py`](graph.py) | Microsoft Graph connector (Outlook.com / Live / Microsoft 365), httpx |
| [`imap.py`](imap.py) | IMAP connector (stdlib imaplib + email) |
| [`jobs.py`](jobs.py) | Mail jobs (queue "mail"): sync, backfill pages, per-message processing |
| [`ledger.py`](ledger.py) | Keep mail_attachments in step with document events |
| [`models.py`](models.py) | Mail tables: accounts, the message ledger, attachments, backfills |
| [`oauth.py`](oauth.py) | OAuth 2 authorization-code + PKCE for Gmail and Microsoft Graph, via plain httpx |
| [`prefilter.py`](prefilter.py) | Deterministic mail rules (mail-rules.yaml) before the triage agent: skip | triage | import |
| [`routes.py`](routes.py) | /api/sources: mail accounts, OAuth, backfills, the triage log |
| [`settings.py`](settings.py) | Mail connector settings (env prefix DOCUHIVE_MAIL_) |

## Extending

Connectors only read mail; documents go into the archive through the ingest entry point.

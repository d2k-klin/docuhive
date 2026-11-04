# CL-04 — Email ingestion: OAuth, connectors, prefilter, triage, backfill (CL-M0 part 2, CL-M4)

**Goal:** documents in Gmail, Outlook/Live and IMAP mailboxes reach the vault automatically, both new mail and a historical backfill, with no duplicates and full provenance (MAIL-01..10).
**Uses:** I4 `ingest.submit`. Use `FakeIngest` until OA-M3 is done. Also I2 jobs and I5 `current_user` (dev user until OA-M4).

## CL-M0 (part 2) — OAuth spike (standalone, `spikes/cl/mail/`)
1. **Google:**
   - Create a Google Cloud project, enable the Gmail API, and set up the OAuth consent screen (External, your account as a test user) with scope `https://www.googleapis.com/auth/gmail.readonly`.
   - Run a loopback-redirect script, then list the messages matching `has:attachment after:2025/01/01` and download one attachment.
   - **Publish the app to "In production"** (unverified is fine for personal use, with a warning screen). Confirm the refresh token survives longer than 7 days (testing-mode tokens expire after 7 days).
2. **Microsoft:**
   - Create an Azure app registration with supported account types "Personal Microsoft accounts only" (or "Any + personal").
   - Platform Web, with redirect `http://localhost:8765/callback`.
   - Delegated permissions: `Mail.Read`, `offline_access`, `User.Read`. Add a client secret.
   - Run an `msal` `ConfidentialClientApplication` auth code flow with authority `https://login.microsoftonline.com/consumers`, call `GET /me/messages?$filter=hasAttachments eq true&$top=10`, and download one attachment.
3. **IMAP:** use `imaplib.IMAP4_SSL` with an app password (e.g. GMX/Web.de/Fastmail): `UID SEARCH SINCE`, then `FETCH BODY.PEEK[]`.
4. Write down the gotchas in `spikes/cl/mail/RESULTS.md`, and turn them into `docs/setup/mail-accounts.md` in CL-M4.

---

## CL-M4 — Email ingestion in the repo

### 4.1 Settings & secrets — `docuhive/mail/settings.py`
`MailSettings`, with env prefix `DOCUHIVE_MAIL_`:
- `TOKEN_KEY`: a Fernet key, required once any account exists. `docuhive mail gen-key` prints one.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`
- `SYNC_EVERY_MIN` (default 15)
- `OVERLAP_MIN` (default 120)
- `MAX_ATTACHMENT_MB` (default 50)

Add the extra `[project.optional-dependencies] mail = [google-auth, msal]`. HTTP calls use `httpx` directly (no heavy Google client library).

### 4.2 Tables (intel migration `0003_mail`)
```sql
CREATE TABLE mail_accounts (
  id               bigserial PRIMARY KEY,
  owner_id         bigint NOT NULL,                  -- users.id (FK)
  provider         text NOT NULL,                    -- gmail | graph | imap
  address          text NOT NULL,
  display_name     text,
  enc_credentials  bytea NOT NULL,                   -- Fernet(JSON: refresh_token | imap password, host, port, …)
  status           text NOT NULL DEFAULT 'active',   -- active | paused | needs_reauth | error
  last_sync_at     timestamptz,
  sync_cursor      jsonb NOT NULL DEFAULT '{}',      -- {"since": "...", "uidvalidity": ..., "last_uid": ...}
  label_on_import  boolean NOT NULL DEFAULT false,
  default_shared   boolean NOT NULL DEFAULT true,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, address)
);
CREATE TABLE mail_messages (
  id                bigserial PRIMARY KEY,
  account_id        bigint NOT NULL REFERENCES mail_accounts(id) ON DELETE CASCADE,
  provider_msg_id   text NOT NULL,
  rfc_message_id    text,
  received_at       timestamptz NOT NULL,
  email_from        text, subject text,
  status            text NOT NULL,      -- new | prefiltered_out | triage_rejected | imported | partial | error
  reason            text,               -- prefilter rule or triage reason
  triage_confidence real,
  ai_run_id         bigint,
  processed_at      timestamptz,
  UNIQUE (account_id, provider_msg_id)
);
CREATE INDEX mail_messages_status ON mail_messages (account_id, status, received_at);
CREATE TABLE mail_attachments (
  id                bigserial PRIMARY KEY,
  message_id        bigint NOT NULL REFERENCES mail_messages(id) ON DELETE CASCADE,
  provider_att_id   text,               -- null for the "body as document" pseudo-attachment
  filename          text NOT NULL, mime text, size int,
  sha256            text,
  document_id       text,               -- from IngestResult
  status            text NOT NULL,      -- skipped | submitted | duplicate | stored | quarantined | error
  reason            text
);
CREATE TABLE backfills (
  id           bigserial PRIMARY KEY,
  account_id   bigint NOT NULL REFERENCES mail_accounts(id) ON DELETE CASCADE,
  date_from    date NOT NULL, date_to date NOT NULL,
  page_token   text,                    -- provider paging state; null = start
  status       text NOT NULL DEFAULT 'running',   -- running | paused | done | cancelled | error
  scanned      int NOT NULL DEFAULT 0, candidates int NOT NULL DEFAULT 0,
  imported     int NOT NULL DEFAULT 0, duplicates int NOT NULL DEFAULT 0, errors int NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz, last_error text
);
```

### 4.3 OAuth flows — `docuhive/mail/oauth.py`, routes under `/api/sources/oauth/*`
- **Start:** `GET /api/sources/oauth/{google|microsoft}/start` generates `state` (random, stored server-side for 10 min, bound to the user) and a PKCE verifier, then redirects to the provider.
- **Callback:** `GET /api/sources/oauth/{provider}/callback?code&state`:
  1. Verify `state`.
  2. Exchange the code for tokens.
  3. Fetch the address (Gmail `users/me/profile`, Graph `/me`).
  4. Create or update `mail_accounts` with the encrypted refresh token.
  5. Redirect to `/sources?connected=<id>`.
- **Redirect URI:** `${DOCUHIVE_PUBLIC_URL}/api/sources/oauth/<provider>/callback`. It must be registered at the provider. Google accepts `https://<host>.<tailnet>.ts.net/...` (a public suffix), or `http://localhost:<port>`.
- **Scopes:**
  - **Gmail:** `gmail.readonly`, plus `gmail.modify` **only** if `label_on_import` is wanted (asked at connect time).
  - **Graph:** `Mail.Read offline_access User.Read`, plus `Mail.ReadWrite` only for categorising.
- **Token refresh:** the access token is cached in memory per account (expiry − 60 s). An `invalid_grant` on refresh sets `status=needs_reauth` and sends a notification (CL-M7). Syncing for that account stops until the user reconnects.
- **IMAP accounts:** `POST /api/sources/accounts` `{provider:"imap", host, port, ssl, username, password, folders}` tests the login before saving it.

### 4.4 Connector interface — `docuhive/mail/base.py`
Three implementations justify a small Protocol:
```python
class MsgRef(NamedTuple): provider_msg_id: str; received_at: datetime

class MailMessage(BaseModel):
    ref: MsgRef
    rfc_message_id: str | None
    email_from: str; to: list[str]; subject: str
    headers: dict[str, str]            # List-Unsubscribe, Precedence, Auto-Submitted, X-Gmail labels…
    labels: list[str]                  # Gmail labels/categories, Graph categories, IMAP folder
    text_snippet: str                  # first 2 KB of text body (HTML stripped)
    has_html_body: bool
    attachments: list[AttachmentMeta]  # {provider_att_id, filename, mime, size, inline: bool}

class Connector(Protocol):
    def list_range(self, since: datetime, until: datetime, page_token: str | None,
                   page_size: int = 100) -> tuple[list[MsgRef], str | None]: ...
    def get_message(self, ref: MsgRef) -> MailMessage: ...
    def download_attachment(self, ref: MsgRef, att: AttachmentMeta, dest: Path) -> None: ...
    def download_raw(self, ref: MsgRef, dest: Path) -> None: ...      # full .eml (for body archiving)
    def mark_imported(self, ref: MsgRef) -> None: ...                 # label/category; no-op if disabled
```
**Incremental sync uses the same `list_range`** over a sliding window (`since = last_sync_at − OVERLAP_MIN`). The ledger's unique `(account_id, provider_msg_id)` makes the overlap harmless. This avoids three provider-specific cursor protocols (Gmail historyId, Graph delta, IMAP CONDSTORE).
<br>`ponytail:` this re-lists the overlap window each sync, which is fine at personal volume. Switch to Gmail `history.list` or Graph delta only if API quotas become a problem.

**Gmail** (`gmail.py`, REST `https://gmail.googleapis.com/gmail/v1/users/me`):
- `list_range`: `GET messages?q=after:<epoch> before:<epoch> -in:chats&maxResults=100&pageToken=`. Epoch seconds are supported in `q`.
- `get_message`: `GET messages/{id}?format=full`. Walk the `payload.parts` tree. An attachment is any part with `filename` and `body.attachmentId`. Inline means `Content-Disposition: inline` + `Content-ID`. Labels come from `labelIds` (`CATEGORY_PROMOTIONS`, `CATEGORY_SOCIAL`, `CATEGORY_UPDATES`, `SPAM`, `TRASH`).
- `download_attachment`: `GET messages/{id}/attachments/{attId}` (base64url `data`).
- `download_raw`: `GET messages/{id}?format=raw`.
- `mark_imported`: create the label `DocuHive/Imported` once, then `POST messages/{id}/modify {addLabelIds}`.
- **Quotas:** about 250 units per user per second. On 429 or 403 `rateLimitExceeded`, back off with jitter. Use `RetryLater` in jobs.

**Microsoft Graph** (`graph.py`, `https://graph.microsoft.com/v1.0/me`):
- `list_range`: `GET messages?$filter=receivedDateTime ge {since} and receivedDateTime lt {until}&$select=id,receivedDateTime&$orderby=receivedDateTime&$top=100`. The page token is the `@odata.nextLink`. This searches all folders except deleted items (`parentFolderId` is checked against the well-known `deleteditems` and `junkemail`, which are excluded).
- `get_message`: `GET messages/{id}?$select=…,internetMessageHeaders,categories,body,hasAttachments`, plus `GET messages/{id}/attachments?$select=id,name,contentType,size,isInline`.
- `download_attachment`: `GET messages/{id}/attachments/{attId}/$value` (works for large files). `itemAttachment` (an attached email) is skipped in v1 with reason `item_attachment_unsupported`.
- `download_raw`: `GET messages/{id}/$value` (MIME).
- `mark_imported`: `PATCH messages/{id} {categories: [...existing, "DocuHive Imported"]}`.
- **Throttling:** 429 with `Retry-After` → `ctx.defer`.

**IMAP** (`imap.py`, stdlib `imaplib` + `email`):
- Folders come from the account config (default `INBOX`). Message ids are `<folder>:<UIDVALIDITY>:<UID>`.
- `list_range`: `UID SEARCH SINCE <dd-Mon-yyyy> BEFORE <dd-Mon-yyyy>` per folder. The page token is `folder index + offset`.
- `get_message` and `download_*`: `UID FETCH <uid> (BODY.PEEK[])`. **PEEK**, so messages are never marked as read. Parse with `email.message_from_bytes(policy=email.policy.default)`.
- `mark_imported`: no-op (IMAP keywords are optional; backlog).
- **UIDVALIDITY change:** log it and treat the folder as new. The ledger dedupe (by `rfc_message_id` as a secondary check) prevents re-imports.

### 4.5 Prefilter — `docuhive/mail/prefilter.py`, `config/defaults/mail-rules.yaml` (CL)
```yaml
version: 1
defaults:
  attachment_mime_allow: [application/pdf, image/jpeg, image/png, image/heic, image/tiff,
                          application/vnd.openxmlformats-officedocument.wordprocessingml.document,
                          application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,
                          application/vnd.oasis.opendocument.text]
  min_attachment_kb: 15          # skips logos / signature images
  skip_inline_images: true
  skip_labels: [CATEGORY_PROMOTIONS, CATEGORY_SOCIAL, SPAM, TRASH]
  skip_if_list_unsubscribe_and_no_attachment: true
  skip_auto_submitted: false
  deny_senders: ["*@*.newsletter.*", "no-reply@marketing.*"]
  allow_senders: []              # always import attachments, skip triage
  body_archive_senders: []       # archive the email body itself (HTML receipts), e.g. "*@amazon.de"
accounts: {}                     # per-address overrides, same keys (deep-merged over defaults)
```
- Sender patterns use `fnmatch` on the lowercased address.
- **Output:** `PrefilterResult(decision: skip | triage | import, reason, candidate_attachments, archive_body: bool)`.
  - `deny` → skip
  - `allow` → import (no triage)
  - no allowed attachment and not `body_archive` → skip
  - otherwise → triage
- Every skip records its reason in `mail_messages.reason` (for example `prefilter:promotions`).

### 4.6 Triage agent — `docuhive/agents/triage.py`, prompt `prompts/triage.md`
- **Input:** from, subject, received date, labels, `text_snippet` (2 KB), and the attachment list (name, mime, size). **Never the attachment content.**
- **Output:**
  ```python
  class TriageOut(BaseModel):
      archive: bool
      attachments: list[str]   # filenames to import (subset)
      archive_body: bool       # body is itself a document (e.g. HTML receipt)
      doc_hint: str | None     # likely document type id
      reason: str = Field(max_length=200)
      confidence: float
  ```
- **Decision:** `archive and confidence >= triage.accept_threshold` (default 0.6) → import. Otherwise status `triage_rejected` with the reason, and the message can be imported manually.
- **Privacy:** `tasks.triage` routes local by default. Email snippets can be sensitive, so if the triage route is non-local, the UI warns at account-connect time.
- Budget-aware like every harness call. During a backfill, `BudgetExceeded` pauses the backfill (status `paused`, `last_error="budget"`).

### 4.7 Jobs
| Kind (queue `mail` unless noted) | Payload | Does |
|----------------------------------|---------|------|
| `mail.sync.all` (`@periodic` every `SYNC_EVERY_MIN`) | `{}` | for each `active` account, enqueue `mail.sync {account_id}` (dedupe `mail.sync:<id>`) |
| `mail.sync` | `{account_id}` | `list_range(last_sync_at − overlap, now)` over all pages. Insert new ledger rows (`status=new`) and enqueue `mail.process` for each new one. Set `last_sync_at = start time of this run` |
| `mail.backfill.page` | `{backfill_id}` | one page of `list_range(date_from, date_to, page_token)`. Insert ledger rows, enqueue `mail.process`, update the counters and `page_token`, then re-enqueue itself (`run_after` +2 s to pace it) until there is no next page → `done`. It checks `status == running` first (pause/cancel take effect) |
| `mail.process` | `{message_id}` | `get_message` → prefilter → (triage, queue `ai` via the harness) → for each selected attachment: `download_attachment(dest=ingest.incoming_dir()/…)`, check `MAX_ATTACHMENT_MB`, compute sha256, check the ledger for the same sha256 on this account (skip as duplicate), then `ingest.submit([path], IngestRequest(owner_id=account.owner_id, shared=account.default_shared, source=SourceInfo(kind=email, original_filename, account_id, message_id, email_from, subject, received_at), hints={"doc_hint": …}))`. Store `document_id` and status. If `archive_body`, `download_raw` → `.eml` → submit (OA renders `.eml`). Then `mark_imported` if enabled. The message status becomes `imported`, `partial` or `error` |
| `document.stored` (shared handler, CL-02) | — | also updates `mail_attachments.status=stored` where `document_id` matches |
| `document.quarantined` | — | updates `mail_attachments.status=quarantined` with the reason |

**Idempotency:**
- `mail.process` on a message whose status is not `new` is a no-op, unless `force=true` (manual "import anyway").
- An attachment with the same sha256 already `stored` for this owner gets `duplicate` from `ingest.submit` anyway.

### 4.8 Sources API (`/api/sources`)
| Endpoint | Notes |
|----------|-------|
| `GET /accounts` · `POST /accounts` (IMAP) · `PATCH /accounts/{id}` (pause, `label_on_import`, `default_shared`, display name) · `DELETE /accounts/{id}` | delete removes the credentials and ledger. **The imported documents stay** |
| `GET /oauth/{provider}/start` · `/callback` | §4.3 |
| `POST /accounts/{id}/sync` | sync now |
| `POST /accounts/{id}/backfills {date_from, date_to}` · `GET /backfills?account_id=` · `POST /backfills/{id}/pause|resume|cancel` | progress counters included |
| `GET /messages?account_id=&status=&q=&cursor=` | the triage log: from, subject, date, status, reason, confidence, attachments (with links to documents) |
| `POST /messages/{id}/import` | "import anyway" → `mail.process` with `force=true`, skipping triage |
| `GET /rules` | effective `mail-rules.yaml` (read-only) |

All endpoints are owner-scoped: you only see your own accounts.

### 4.9 Sources UI — `app/(app)/sources/` (CL)
- **Accounts list:** provider icon, address, status (`needs_reauth` → a "Reconnect" button), last sync, "Sync now", pause toggle.
- **Connect:** buttons for Gmail and Microsoft (OAuth start), and an IMAP form. Before connecting, it shows what will be accessed (read-only, nothing deleted) and the privacy note about where triage runs.
- **Backfill dialog:** date range (native date inputs) with presets (last year, last 3 years, since 2015). It shows an estimate after the first page (scanned per page × pages so far).
- **Backfill progress:** a progress card with the counters, pause/resume/cancel, and auto-refresh every 5 s.
- **Triage log:** a filterable table. Each row expands to the reason, and offers "Import anyway" for rejected or prefiltered messages.
- **Dashboard widget** (in `IntelDashboardWidgets`): accounts OK/needing attention, and documents imported from mail in the last 7 days.
- **Nav:** uncomment "Sources".
- **Docs:** `docs/setup/mail-accounts.md`, step by step for Google Cloud and Azure (from the CL-M0 spike), with screenshots optional.

### 4.10 Setup & guidance
- **`GET /api/sources/setup-status`**:
  - `mail.accounts` (`optional`, but recommended; action "Connect email")
  - `mail.reauth` (`error` per account needing reauth, action "Reconnect")
  - `mail.backfill` (`todo` until a first backfill has been offered and either run or declined)
  - `mail.triage_privacy` (`warn` if the triage route is non-local)
- **"Email" wizard step** appended to `intelSetupSteps`, in this order:
  1. explain read-only access
  2. connect
  3. pick a rules preset (Recommended / Everything with attachments / Only allow-listed senders)
  4. choose the backfill range with an estimate
  5. "what happens now"
- Every sources error code gets user copy (the `guided-experience` skill), e.g. `needs_reauth`, `oauth_denied`, `imap_login_failed`.

### 4.11 Tests
- Connectors, tested with **recorded fixtures**: JSON responses under `tests/intel/fixtures/gmail/` and `graph/`, served by `httpx.MockTransport`. IMAP uses a fake `IMAP4_SSL` class serving `.eml` fixtures. Cover:
  - paging
  - nested multipart
  - inline vs attachment
  - a large Graph attachment via `$value`
  - `itemAttachment` skipped
  - an expired token → `needs_reauth`
- Prefilter: a rule table test (deny, allow, labels, list-unsubscribe, min size, body archive, per-account override).
- Triage with FakeModel: accept, reject, partial attachment selection, below-threshold rejection.
- Ledger and idempotency: running sync twice over the same window → no new `mail.process` jobs. Backfill resumes from `page_token` after a simulated crash. An attachment whose duplicate sha256 is seen across two messages is imported once.
- Pause and cancel take effect at the next page.
- Contract tests: with the real OA `ingest.submit` (once I4 is done), an `.eml` body archive ends up `stored`.

## Acceptance (J2)
- A Gmail account and an Outlook.com account are connected through the UI. A 1-year backfill runs to `done`.
- Re-running the same backfill gives `imported = 0` and only duplicates/no-ops.
- Killing the worker mid-backfill, then restarting it, resumes and completes it with no duplicate documents.
- Triage decisions are visible with reasons. "Import anyway" works.
- No email is modified unless `label_on_import` is on (verified with the read-only scopes).

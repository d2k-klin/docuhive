# CL-06 — Reminders, notifications, privacy audit (CL-M7)

**Goal:** DocuHive tells you about upcoming deadlines and problems (QA-05, AUTO-03), and the privacy guarantee (AI-03) is proven by tests and visible to the user.
**Uses:** I3 events, and `doc_facts` (read-only).

## 7.1 Notification channels — `docuhive/notify/`
```python
class Notification(BaseModel):
    kind: str            # reminder | job_dead | quarantine | review_backlog | mail_reauth | budget | backup
    title: str
    body: str            # plain text, no document content beyond the title (privacy)
    url: str | None      # deep link, e.g. ${PUBLIC_URL}/documents/<id>
    priority: Literal["low", "default", "high"] = "default"
    user_id: int | None  # None = all admins

def send(n: Notification) -> None: ...   # fan-out to the user's enabled channels; logs failures, never raises
```
- **Built-in channels:**
  - **ntfy:** `POST {server}/{topic}`, with the headers `Title`, `Priority`, `Click`, and an optional `Authorization: Bearer`. ntfy can be self-hosted or ntfy.sh.
  - **email:** SMTP (stdlib `smtplib`), with host, port, STARTTLS, user and password.
- **Plugin channels** (Telegram, Pushover, Matrix…) come via `config.plugins("notify_channel")` and implement `send(config: dict, n: Notification)`.
- Table (intel migration `0006_notify`):
  - `notification_channels(id, user_id, kind, config_enc bytea, enabled, created_at)`. The config is Fernet-encrypted with `DOCUHIVE_MAIL_TOKEN_KEY`, or a separate `DOCUHIVE_AI_NOTIFY_KEY` (decide in the PR and document it).
  - `notification_log(id, at, user_id, kind, title, channel_id, ok, error)`.
- **Rate limit:** the same `(kind, dedupe subject)` is sent at most once per 24 h (e.g. `review_backlog`).
- **API** `/api/notifications`: list, create and delete channels, `POST /channels/{id}/test`, and `GET /log`.
- **UI** `app/(app)/settings/notifications/`: channels, a test button, per-kind toggles (stored in the channel config), and the recent log. Nav: uncomment "Settings → Notifications".

## 7.2 What triggers notifications
| Kind | Source | Rule |
|------|--------|------|
| `reminder` | §7.3 | per reminder date |
| `quarantine` | `document.quarantined` handler | immediately, to the owner |
| `job_dead` | periodic `notify.scan_dead_jobs` (hourly, reading OA's `jobs` table read-only) | new dead jobs since the last scan, to admins. **Read-only use of a core table is allowed** (contracts §5) |
| `review_backlog` | periodic daily | pending review items > `notify.review_backlog_threshold` (default 25) |
| `mail_reauth` | CL-04 token refresh failure | immediately |
| `budget` | CL-01 budgets | at 80% and at 100%, once per provider per month |
| `backup` | periodic daily: reads `vault/_system/backup-status.json` (OA writes it) | the last success is older than 48 h, to admins |

## 7.3 Reminders — `docuhive/reminders/`
- **Source:** taxonomy facts with `remind_days_before` (contracts §1 `FactField`). Defaults are in the CL-02 taxonomy: invoice `due_date`, contract `end_date`, insurance `renewal_date`, ID `expiry_date`, warranty `warranty_end`, tax `due_date`.
- **Derived deadline:** for contracts with `end_date` and `notice_period_days`, add a "notice deadline" = `end_date − notice_period_days`, reminded `[30, 7]` days before.
- Table (intel migration `0007_reminders`):
  ```sql
  CREATE TABLE reminders (
    id bigserial PRIMARY KEY, document_id text NOT NULL,   -- FK documents(id) ON DELETE CASCADE
    fact text NOT NULL, label text NOT NULL,               -- "Notice deadline", "Due date", ...
    due_on date NOT NULL, remind_on date NOT NULL,
    status text NOT NULL DEFAULT 'scheduled',              -- scheduled | sent | dismissed | done
    sent_at timestamptz,
    UNIQUE (document_id, fact, remind_on)
  );
  ```
- **Job `reminders.sync {document_id}`:** triggered by `document.metadata_changed` when the `fields` include facts, and after extract. It recomputes that document's reminders: deletes `scheduled` rows that no longer apply, and inserts new ones. Past `remind_on` dates are not created.
- **Periodic `reminders.scan`** (daily at 07:00 local, `TZ` setting): rows with `remind_on <= today AND status='scheduled'` and a document visible to its owner (not trashed) → `notify.send` to the document owner → status `sent`.
- **API** `/api/reminders`: `GET ?from=&to=` (upcoming, owner/visible-scoped), `POST /{id}/dismiss`, `POST /{id}/done`.
- **UI:**
  - `app/(app)/reminders/`: an upcoming list grouped by month (label, document link, due date, days left), with Dismiss and Done.
  - A dashboard widget "Next deadlines" (top 5) in `IntelDashboardWidgets`.
  - Nav: uncomment "Reminders".
- **Calendar export:** `GET /api/reminders.ics?token=<api token with read scope>`, an iCalendar feed of the upcoming reminders (hand-written ICS, about 20 lines, no library), so the deadlines show up in your phone calendar. Document it in `docs/setup/notifications.md`.

## 7.4 Privacy audit (AI-03) — tests and visibility
1. **Test suite** `tests/intel/test_privacy_audit.py`:
   - It seeds documents in restricted categories (`health/*`, `government/identity`, `insurance/health`), one with the restricted tag, and one unrestricted.
   - It configures routing with **only cloud routes** for every task, then runs the classify, extract, embed, chat (read_document, search) and analyse flows using FakeModel instances flagged non-local.
   - **Assert:**
     - no FakeModel non-local instance ever received the text of a restricted document (the fake records its inputs)
     - every `ai_runs` row with `restricted=true` has `local=true` (the DB constraint)
     - skipped tasks produce review notices
   - Then it repeats the runs with a local route available and asserts that they are processed locally.
2. **Triage prompt check:** email snippets go only to the `triage` route. Test that a non-local triage route prompts the connect-time warning flag in the account API response.
3. **Usage UI** (`settings/ai`, from CL-M1): add a "Privacy" card showing, for this month, the runs by local/cloud, the restricted runs (all local), and documents skipped for privacy, with a link to the list.
4. **Cross-check with OA's security checklist** (OA-M8 §8.1): tick "CL privacy tests green".

## 7.5 Setup & guidance
- `GET /api/notifications/setup-status`: `notifications.channel` (`optional`; "Get told about deadlines and problems").
- A "Notifications" wizard step is appended to `intelSetupSteps`: pick ntfy or email, send a test message, toggle the kinds.

## 7.6 Tests
- ntfy and SMTP channels: requests built correctly (mock transport / a fake SMTP server via `aiosmtpd`, or a monkeypatched `smtplib`).
- Rate limit and dedupe. A plugin channel loaded from an entry point.
- Reminder computation (notice deadline, past dates skipped, recompute on change), the scan sends once, a trashed document is not reminded.
- ICS output is validated by parsing it back (a simple line check; no library required).

## Acceptance
- A contract with `end_date` 2027-03-31 and `notice_period_days: 90` produces "Notice deadline 2026-12-31" reminders on 2026-12-01 and 2026-12-24, sent to ntfy on those days. Use a time-frozen test plus one real ntfy test message.
- The privacy audit test suite is green and part of CI.
- The calendar feed subscribes successfully in iOS/macOS Calendar.

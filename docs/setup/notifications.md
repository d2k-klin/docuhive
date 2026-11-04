# Notifications and reminders

DocuHive can tell you about deadlines found in your documents (invoice due dates, contract notice periods, insurance renewals, ID expiry) and about problems (a file it couldn't read, a mail account that needs reconnecting, a stale backup). Messages contain only titles and links, never document content.

## Channels

Add channels in **Settings → Notifications**, then press **Send test**.

| Channel | You need |
|---------|----------|
| **ntfy** (push to phone or desktop) | a topic name. The server is `https://ntfy.sh` by default, or your own ntfy server, plus an access token if the topic is protected. Install the ntfy app and subscribe to the same topic |
| **Email** | an SMTP host, port (default 587, STARTTLS), optional username and password, a "from" and a "to" address |

Each channel can be limited to certain kinds of messages (for example reminders only). Channel settings are stored encrypted. Set `DOCUHIVE_AI_NOTIFY_KEY` in `.env` (generate one with `uv run docuhive mail gen-key`).

## Reminders

- DocuHive creates reminders automatically from the dates it extracts. You can see them under **Reminders**, and dismiss them or mark them done.
- Reminders are sent at 07:00 in your time zone (`DOCUHIVE_AI_TZ`, default `Europe/Berlin`).
- When to remind is set per document type in the taxonomy (`remind_days_before`, for example 30 and 7 days before a contract's notice deadline).

## Calendar feed

To see your deadlines in your phone or desktop calendar:
1. Create a personal API token with the **read** scope in **Settings → Tokens**.
2. Subscribe to `<your DocuHive address>/api/reminders.ics?token=<token>` in your calendar app (iOS/macOS: Settings → Calendar → Accounts → Add subscribed calendar).

Treat this link like a password: anyone with it can read your reminder titles. Revoke the token to stop it working.

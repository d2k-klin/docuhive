# Email accounts

DocuHive reads your mailbox **read-only**, finds attachments that are real documents (invoices, contracts, statements), and archives them. It never deletes or moves your emails. Labelling imported mail is optional and off by default.

## 1. Create the encryption key (once)

Mail passwords and sign-in tokens are stored encrypted. Generate a key, then add it to `.env`:

```bash
uv run docuhive mail gen-key
```
It prints the key alone; add it to `.env` as `DOCUHIVE_MAIL_TOKEN_KEY=<key>`. Keep this key safe: without it, the saved accounts can't be used and have to be connected again.

## 2. Gmail

You create your own small Google app, so that only you have access.

1. Open <https://console.cloud.google.com>, create a project, and enable the **Gmail API**.
2. Set up the **OAuth consent screen**: External, add your own address as a test user, and add the scope `https://www.googleapis.com/auth/gmail.readonly`. Add `gmail.modify` only if you want imported mails labelled.
3. **Publish the app** ("In production"). Google shows an "unverified app" warning for personal use; that is expected. In "Testing" status, access expires every 7 days.
4. Create credentials: **OAuth client ID → Web application**, with the redirect URI `<your DocuHive address>/api/sources/oauth/google/callback` (for example `https://docuhive.<tailnet>.ts.net/api/sources/oauth/google/callback`).
5. Add `DOCUHIVE_MAIL_GOOGLE_CLIENT_ID` and `DOCUHIVE_MAIL_GOOGLE_CLIENT_SECRET` to `.env`, and restart.

## 3. Outlook, Hotmail, Live (Microsoft)

1. Open <https://portal.azure.com> → **App registrations → New registration**. For a personal account, choose "Personal Microsoft accounts only".
2. Add the redirect URI (platform **Web**): `<your DocuHive address>/api/sources/oauth/microsoft/callback`.
3. Under **API permissions**, add the delegated permissions `Mail.Read`, `offline_access` and `User.Read`. Add `Mail.ReadWrite` only if you want imported mails categorised.
4. Under **Certificates & secrets**, create a client secret.
5. Add `DOCUHIVE_MAIL_MS_CLIENT_ID` and `DOCUHIVE_MAIL_MS_CLIENT_SECRET` to `.env`. Set `DOCUHIVE_MAIL_MS_TENANT=consumers` for personal accounts (the default `common` allows both personal and work accounts). Then restart.

## 4. Other providers (IMAP)

For mailboxes such as GMX, Web.de or Fastmail, create an **app password** in your provider's security settings. Then choose **Connect IMAP** in DocuHive and enter the server, the port (usually 993) and the app password. Outlook.com no longer accepts IMAP passwords; use the Microsoft option instead.

## 5. Connect and choose what to import

In the app, go to **Sources → Connect**. After connecting:
- **Rules:** the defaults skip newsletters, promotions, small logos and inline images. Your private overlay's `mail-rules.yaml` can allow or deny specific senders.
- **Backfill:** pick a date range for older mail (for example "last 3 years"). Progress is shown, and you can pause, resume or cancel it. Running it again never imports duplicates.
- **New mail** is checked every 15 minutes (`DOCUHIVE_MAIL_SYNC_EVERY_MIN`).
- **Triage log:** shows every email that was skipped, and why. "Import anyway" imports a skipped message.

## Troubleshooting

| You see | What to do |
|---------|------------|
| "Reconnect" on an account | the sign-in expired or was revoked: click Reconnect |
| Google access expires after a week | the Google app is still in "Testing": publish it (step 2.3) |
| `redirect_uri_mismatch` | the redirect URI at Google/Microsoft must match your DocuHive address exactly, including `https` |
| Encryption key missing | complete step 1 |

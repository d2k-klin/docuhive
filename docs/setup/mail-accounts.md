# Email accounts

DocuHive reads your mailbox **read-only**, finds attachments that are real documents (invoices, contracts, statements), and archives them. It never deletes or moves your emails. Labelling imported mail is optional and off by default.

## Connect a mailbox

Open **Sources** and choose **Gmail**, **Outlook**, **iCloud Mail**, or **Other email**.
The connection guide opens automatically when you have no mailboxes.

1. **Choose your provider.** Gmail and Outlook offer their normal provider sign-in when the server is configured. Your provider password stays with Google or Microsoft.
2. **Connect securely.** If Google sign-in is unavailable, use a Google app password. iCloud and Yahoo also require app passwords; the form links to account security settings. For other providers, enter your address and password. Known servers are filled in automatically. For custom domains, enter the actual mail server under **Server settings**; DocuHive does not guess it from your domain. You can also specify a different username and the folders to watch. Connections use encrypted IMAP on port 993 by default. The login and selected folders are tested before the connection is saved.
3. **Import attachments.** The first sync is queued immediately. Choose the last 30 days, last year, last three years, or custom dates to import older attachments, then choose **Import attachments**. **Skip for now** leaves the connection watching new mail. You can reopen **Import history** at any time.

- **Gmail, iCloud and Yahoo:** use an app password, not your normal account password. Google requires 2-Step Verification before app passwords are available; some managed accounts do not allow them.
- **GMX and WEB.DE:** enable POP3/IMAP in your provider settings first.
- **Outlook, Hotmail and Live:** use Microsoft sign-in. Password-only connections are not offered for these accounts.
- **Only a few emails?** Create a dedicated folder such as `Documents` in your existing mailbox, select it under **Folders to watch**, and move or forward the mail you want to archive into it. DocuHive only reads that folder. There is no separate DocuHive email intake address.

If provider sign-in is unavailable, expand **Set up Google/Microsoft sign-in on this server** for the registration steps and your server's exact callback address. The encryption-key prerequisite also appears before you connect. These are one-time administrator tasks, described below.

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

For mailboxes such as GMX, Web.de or Fastmail, create an **app password** in your provider's security settings. Then choose **Other email** in DocuHive and enter the server under **Server settings**, the port (usually 993) and the app password. Outlook.com no longer accepts IMAP passwords; use the Microsoft option instead.

## 5. Connect and choose what to import

After connecting:
- **Rules:** the defaults skip newsletters, promotions, small logos and inline images. Your private overlay's `mail-rules.yaml` can allow or deny specific senders.
- **Backfill:** pick a date range for older mail (for example "last 3 years"). Progress is shown, and you can pause, resume or cancel it. Running it again never imports duplicates.
- **New mail** is checked every 15 minutes (`DOCUHIVE_MAIL_SYNC_EVERY_MIN`).
- **Email activity:** shows every email that was skipped, and why. "Import anyway" imports a skipped message.

## Troubleshooting

| You see | What to do |
|---------|------------|
| "Reconnect" on an account | the sign-in expired or was revoked: click Reconnect |
| Google access expires after a week | the Google app is still in "Testing": publish it (step 2.3) |
| `redirect_uri_mismatch` | the redirect URI at Google/Microsoft must match your DocuHive address exactly, including `https` |
| Encryption key missing | complete step 1 |

## Why this flow

[Paperless-ngx](https://docs.paperless-ngx.com/usage/#incoming-mail) separates mail accounts from import rules, including folder scope and attachment filters. [Docspell](https://docspell.org/docs/webapp/scanmailbox/) separates mailbox setup from scanning. DocuHive uses the same account-and-import distinction, with a provider chooser and an explicit history range. [Papra](https://docs.papra.app/) also offers forwarding to a generated intake address; DocuHive currently connects directly to your mailbox instead.

# Import from Paperless-ngx (`paperless-import`)

> **Status: available.**

**Overview.** Moving from Paperless-ngx to DocuHive without losing anything. The plugin reads your Paperless archive through its API and brings every document over: the original file, its title, date, correspondent and tags. DocuHive then reads each one like your own uploads, so amounts, due dates and deadlines are found and the plugins can use them. Paperless itself is only read, never changed.

## Who it is for

Anyone with a Paperless-ngx archive who wants to try or switch to DocuHive. Run both side by side for as long as you like.

## What it does

- **Every document you can see in Paperless,** imported into the archive of the administrator who starts it, as private documents.
- **Your work in Paperless is kept:** title, date, correspondent and tags are taken over as your own values, so DocuHive's AI never overwrites them. Paperless document types become tags (`paperless:Invoice`), because the two archives name types differently.
- **Read like an upload:** text recognition, search, and (if you leave it on) the AI reads amounts, dates and deadlines. Health and identity documents are read only by a local model, as always.
- **Safe to repeat:** the same file is never imported twice. Stop the import at any time and start again; it continues where it stopped.
- **Progress and problems** on one page: how many are imported, already here, or failed, and why.

## Set it up

1. In Paperless, open your profile (top right) and copy the **API Auth Token**.
2. Add the plugin and switch it on ([how](../README.md#use-a-plugin)). It asks to reach one address: the one you enter in its settings.
3. Under **Settings → Plugins → Import from Paperless-ngx**, enter the Paperless address (for example `http://192.168.1.20:8000`) and the token.
4. Open **Paperless import**, press **Check the connection**, then **Start the import**.
5. When it is finished, switch the plugin off. Imported documents stay.

Only an administrator sees the import page.

## Make it yours

| What | Where |
| --- | --- |
| Address, token, AI reading, types as tags | **Settings → Plugins** |
| The page | `pages/import.yaml` |

## Limits

- Notes, custom fields, permissions and saved views from Paperless are not imported.
- Each document goes into one person's archive; share documents afterwards if the household should see them.
- A very large archive takes as long as reading every document takes on your hardware; the AI step is the slow part. Turn it off in the settings to import first and read later.

## What's here

| Path | What it is |
| --- | --- |
| `plugin.yaml` | Settings, and the one address it may reach |
| `plugin.py` | Checking, the import in steps, progress |
| `migrations/` | What was imported, and each run |
| `pages/import.yaml` | The import page |
| `tests/` | Its tests, against a small stand-in for Paperless |

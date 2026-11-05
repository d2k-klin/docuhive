# Install DocuHive

This guide takes you from an empty Linux host to a signed-in household archive, in order. Each step links to the guide with the details; follow them in the order below.

To try DocuHive on your own computer first, use the [quick start](../../README.md#quick-start) instead. It runs a development copy with test settings, not something to keep real documents in.

> DocuHive is not yet accepted for real documents: three nightly backups, a host-loss rehearsal and phone and NAS checks on the target hardware are still open. See [production readiness](../shared/production-readiness.md).

## What you need

| Thing | Why |
| --- | --- |
| A Linux host with an SSD | Runs the containers; the database and the upload staging area live on the SSD |
| Docker Engine with Compose 2.24 or newer | Runs DocuHive |
| A NAS or a second disk | Holds the vault, the folder with your documents |
| [Tailscale](https://tailscale.com) on the host and on your phones | Private HTTPS, with no ports opened on your router |
| [restic 0.18.1](https://github.com/restic/restic/releases/tag/v0.18.1) and a backup disk or remote | Nightly backups |
| Optional: 16–32 GB RAM for [Ollama](https://ollama.com) | Local AI, so private documents never leave the house |

## 1. Prepare the host

Clone the repository to `/opt/docuhive`, create the `docuhive` user and the SSD folders. See [Prepare a Linux host](operations.md#prepare-a-linux-host), up to `.env.production`.

## 2. Mount the vault

Mount the NAS share at `/srv/docuhive/vault` with systemd, and check it with `findmnt`. See the [NAS guide](nas-wd-ex2-ultra.md), steps 1–5. Don't write anything into the empty folder while the NAS is not mounted.

**No NAS?** Use a folder on a local disk instead. Ideally pick a second disk, not the system disk, and set `DOCUHIVE_VAULT_HOST_DIR` to it. The vault is the same plain folder tree either way: one folder per year and one per document, with the untouched original, the searchable PDF and `meta.json`. DocuHive writes each file once and never edits or deletes an original; trashed documents keep their files. **Storage health** shows the location and, on a Linux host, whether it is a network share or a local disk. With no second copy on a NAS, the [nightly backup](operations.md#nightly-backups) matters even more.

DocuHive never switches storage on its own. When the configured storage is unavailable, new uploads wait in SSD staging, and they are stored once the storage is back. A silent switch to a local folder would split the archive in two.

## 3. Write the configuration

DocuHive reads two private files. Neither belongs in the repository.

- **`/opt/docuhive/.env.production`** (mode 600): images, database password, secret key, HTTPS address and storage paths. The variable list is in the [operations guide](operations.md#prepare-a-linux-host).
- **`/etc/docuhive/app.env`** (mode 600, owner `docuhive`): AI keys, mail sign-in apps and other private settings. All containers that do work read it; the values from `.env.production` always win. Set `DOCUHIVE_APP_ENV` in `.env.production` to keep it somewhere else.

Create it empty:

```bash
sudo install -d -m 755 /etc/docuhive
sudo install -m 600 -o docuhive -g docuhive /dev/null /etc/docuhive/app.env
```

Then add lines with an editor, using the names from these guides. They say `.env`; in production the same lines go in `app.env`.

- [AI providers](ai-providers.md): `DOCUHIVE_AI_OLLAMA_HOST` and the cloud keys you want. Inside a container, `localhost` is the container itself: point `DOCUHIVE_AI_OLLAMA_HOST` at the address of the machine running Ollama, such as its LAN or tailnet address, and let Ollama listen there.
- [Email accounts](mail-accounts.md): the Google or Microsoft app you created.
- [Notifications](notifications.md): push and email settings.

The two encryption keys need the DocuHive image, so they come in the next step.

## 4. Build and start

```bash
make images PROD_ENV=.env.production
```

Generate the encryption key for mail credentials with the image you just built:

```bash
docker compose --env-file .env.production -f deploy/compose.yml run --rm --no-deps api mail gen-key
```

It prints a new key. Add it to `app.env` as `DOCUHIVE_MAIL_TOKEN_KEY=<key>`. Run the command again for the notification key, and add that one as `DOCUHIVE_AI_NOTIFY_KEY=<key>`. Keep a copy of both keys somewhere other than this host: without them, saved mail accounts and notification channels have to be set up again.

```bash
make up PROD_ENV=.env.production
```

The database migrations run first; the API, workers and web app start once they finish. `make logs PROD_ENV=.env.production` follows the logs.

## 5. Create the first administrator and register the vault

The image's command is `docuhive`, so one-off commands run in a fresh API container:

```bash
docker compose --env-file .env.production -f deploy/compose.yml run --rm api user create admin --admin
```

It asks for a password (at least 12 characters). Then register the mounted vault once:

```bash
docker compose --env-file .env.production -f deploy/compose.yml run --rm api vault init
```

This writes `_system/VAULT_ID` on the NAS and stores the same ID in the database. Uploads, the scanner folder and backups refuse to run against a vault with a missing or different ID, so an unmounted NAS can never be written to by mistake.

Create an account for each household member the same way, without `--admin`. There is no sign-up page.

## 6. Turn on HTTPS

Serve the web app over your tailnet and set the resulting `https://…ts.net` address as `DOCUHIVE_PUBLIC_URL`. See [private HTTPS](remote-access.md). Then run `make up PROD_ENV=.env.production` again so the containers pick up the address.

Check that DocuHive listens on loopback only:

```bash
sudo ss -tlnp
```

The only DocuHive line is `127.0.0.1:3000`.

## 7. Sign in and finish setup

Open the HTTPS address and sign in. The dashboard's **Set up your archive** card lists what is still missing, each with one next step:

- Connect your storage (the vault from step 5)
- Back up your archive (step 8)
- AI, AI provider, and a local model for private documents
- Email accounts, and the encryption key for their credentials
- Notifications
- Automatic filing, which stays off until the AI has proven itself on your own documents

To add the phone app, follow [capture](mobile.md#install-on-your-phone).

## 8. Turn on nightly backups

Create the restic repositories, `/etc/docuhive/backup.env` and the password file, install the systemd timer and run one backup by hand. See [Nightly backups](operations.md#nightly-backups). The dashboard warns you when the last good backup is more than 48 hours old.

## 9. Check it end to end

1. Upload a scanned letter on **Upload** and wait for **Stored**.
2. Find it on **Search** by a word from its text.
3. Open it and check its preview and details.
4. Run the [NAS outage drill](../../deploy/drills/nas-down.md) and the other [drills](../../deploy/drills/README.md) before you rely on it.

Then read the [user guide](../user-guide.md). Upgrades are in [Upgrade and roll back](operations.md#upgrade-and-roll-back).

## When something goes wrong

| What you see | What to do |
| --- | --- |
| `make up` says a variable is missing | A required line in `.env.production` is empty; the message names it. |
| A container refuses to start, saying a path does not exist | The NAS or an SSD folder is not mounted or not created. DocuHive never creates missing host paths. |
| Sign-in works on the host but not on the phone | `DOCUHIVE_PUBLIC_URL` is not exactly the `https://…ts.net` address. |
| Uploads end in **Quarantine** with "Text recognition failed" | Check the OCR worker's logs: `make logs PROD_ENV=.env.production`. |
| AI or mail settings are ignored | They are in the wrong file. They go in `app.env`, not `.env.production`. Restart with `make up`. |
| "No AI provider is reachable yet" with Ollama running | `DOCUHIVE_AI_OLLAMA_HOST` points at `localhost`; use the Ollama machine's address. |

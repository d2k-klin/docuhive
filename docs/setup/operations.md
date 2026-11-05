# Run and recover DocuHive

This is the production stack and runbook. Real document intake and vault initialisation
are prerequisites for storing real files. Phone/NAS acceptance, three consecutive nightly
backups and a full host-loss rehearsal remain release gates, not results implied by this guide.

## Prepare a Linux host

Use Docker Engine with Compose 2.24 or newer, a supported Python 3, Tailscale, and the pinned
[restic 0.18.1 release](https://github.com/restic/restic/releases/tag/v0.18.1). Verify its
published SHA-256 before installing it; the backup script refuses other versions. No
installer is downloaded or run by this repository. Docker builds use digest-pinned bases
and the committed Python/npm locks.

Put the checkout in `/opt/docuhive`. Run host tasks as a dedicated `docuhive` user (UID/GID
1000) with access to the Docker socket. Create the SSD directories with the correct owners:

```sh
sudo install -d -o 1000 -g 1000 -m 700 /srv/docuhive/staging /srv/docuhive/overlay /srv/docuhive/backup /var/cache/docuhive
sudo install -d -o 999 -g 999 -m 700 /srv/docuhive/pg
```

Mount the NAS using the [NAS guide](nas-wd-ex2-ultra.md). Do not create or initialise the
vault underneath an absent mount. Keep the backup password and an independent backup of the
private configuration/mail encryption key off this host too; encrypted mail tokens cannot be
recovered without their original key.

Create a private `.env.production` in the checkout (mode 600), using these variable names:

```dotenv
DOCUHIVE_IMAGE=docuhive:<checked-out-git-sha>
DOCUHIVE_WEB_IMAGE=docuhive-web:<checked-out-git-sha>
POSTGRES_PASSWORD=<random-password>
DOCUHIVE_DATABASE_URL=postgresql+psycopg://docuhive:<url-encoded-password>@postgres:5432/docuhive
DOCUHIVE_SECRET_KEY=<at-least-32-random-bytes>
DOCUHIVE_PUBLIC_URL=https://your-host.your-tailnet.ts.net
DOCUHIVE_VAULT_HOST_DIR=/srv/docuhive/vault
DOCUHIVE_STAGING_HOST_DIR=/srv/docuhive/staging
DOCUHIVE_PG_HOST_DIR=/srv/docuhive/pg
DOCUHIVE_OVERLAY_HOST_DIR=/srv/docuhive/overlay
DOCUHIVE_CONSUME_DEFAULT_OWNER=
```

Replace every placeholder. `POSTGRES_PASSWORD` and the password embedded in the URL must
match. Compose fails on missing required values. Keep immutable image references; use a
new SHA tag for each checkout rather than overwriting one tag. AI keys, mail OAuth apps and
notification settings go in `/etc/docuhive/app.env` (mode 600, or the path in
`DOCUHIVE_APP_ENV`), which every backend container reads; the values above always win. The
[installation guide](installation.md#3-write-the-configuration) lists what goes there.

```sh
make images PROD_ENV=.env.production
make up PROD_ENV=.env.production
```

Migrations run before API and workers. Create the first administrator with
`docker compose --env-file .env.production -f deploy/compose.yml run --rm api user create <name> --admin`,
register the mounted vault with `... run --rm api vault init`, then use [private HTTPS](remote-access.md). API, workers, converter
and database have no published ports. Web binds loopback. PostgreSQL's image-owned UID 999
and Gotenberg's UID 1001 differ from the app's UID 1000; all are non-root. API/workers have
outbound networking for configured providers; the converter and database have only the
internal network. Roots are read-only, with explicit writable volumes/tmpfs.

Check what the host exposes after every install or upgrade:

```bash
sudo ss -tlnp
```

DocuHive's only listener is `127.0.0.1:3000` (the web app). Anything else on `0.0.0.0` or
`[::]` must be a service you chose, such as SSH or Tailscale. A DocuHive port there means
the Compose file was changed; put it back on loopback.

`make logs` follows logs; `make down` stops the stack without deleting data. No production
command removes volumes. Production database downgrades are refused.

## Nightly backups

Initialise each restic repository yourself, on a separate disk or remote target. Test its
access before enabling the timer. Create `/etc/docuhive/restic-password` (owner `docuhive`,
mode 600) and `/etc/docuhive/backup.env` (mode 600):

```dotenv
DOCUHIVE_PROD_ENV=/opt/docuhive/.env.production
DOCUHIVE_VAULT_HOST_DIR=/srv/docuhive/vault
DOCUHIVE_STAGING_HOST_DIR=/srv/docuhive/staging
DOCUHIVE_VAULT_ID=<registered-id-from-_system/VAULT_ID>
DOCUHIVE_BACKUP_STATE_DIR=/srv/docuhive/backup
RESTIC_REPOSITORIES="/mnt/usb/restic b2:bucket:docuhive"
RESTIC_PASSWORD_FILE=/etc/docuhive/restic-password
RESTIC_CACHE_DIR=/var/cache/docuhive
```

Add the remote target's credentials through its documented environment variables in that
same private file. Install the units in `deploy/systemd/`, adjust paths if necessary, run
`systemctl daemon-reload`, then enable `docuhive-backup.timer`. Its 03:00 schedule uses the
host timezone, has a short random delay and catches a missed run after boot. Mount the USB
target before use; add its path to the service's `RequiresMountsFor` and `ReadWritePaths`.

The script locks on SSD, checks the vault ID, stops running API/workers, creates and validates
a custom-format database dump, and backs up the vault **and SSD staging** to each target.
Writers are paused during backup to keep DB/file state consistent; capture keeps its local
queue during that window. Writers are restarted on failure too. The generated library is
excluded. Fourteen database dumps are kept. On Sundays, restic keeps 7 daily, 8 weekly and
24 monthly snapshots and prunes older backup data. On the first of the month it checks 5%
of stored data. Originals and staged files are never pruned by this script.

Run the service once with `systemctl start docuhive-backup.service`, then inspect its journal
and `_system/backup-status.json`. Repository addresses, credentials and raw errors are omitted
from status. The authenticated setup-status endpoint and shell warn on a failed attempt or a
last successful backup older than 48 hours. A missing marker prevents status writes as well
as backups. Store the private configuration independently; the vault backup excludes the
separate overlay directory. Record three successful nights before release acceptance.

For a manual `make backup`, export the variables from the trusted backup environment first;
`PROD_ENV` selects the matching Compose file environment. Never print that environment.

## Upgrade and roll back

1. Keep the current private env file. Check out the next release in `/opt/docuhive`, make a
   second env file with new immutable image tags, and keep storage paths, credentials and
   Compose project name unchanged. Do not combine a PostgreSQL major upgrade with an app update.
2. Export the trusted backup environment, then run
   `make upgrade PROD_ENV=.env.production NEXT_ENV=.env.next`.
3. The helper validates both configurations, builds the checked-out release, stops web and
   writers, takes a quiesced backup, runs core then intelligence migrations and starts the
   new services. Check sign-in, a stored document, search and queued uploads.
4. Keep the pre-upgrade snapshot and both image tags until the checks pass. Point subsequent
   operations and the timer's `DOCUHIVE_PROD_ENV` at the new env file.

Failure before migration restarts the old services. Failure after migration leaves writers
stopped: use the [restore runbook](../../deploy/scripts/restore.md) to restore the matching DB,
vault and staging snapshot into fresh directories before starting the old images. Never run
old code against a possibly migrated production database. The disposable integration test
exercises the v0.1.0 schema → current migration path with document metadata, facts, password
hashes and token scopes preserved; it does not prove a host or NAS recovery.

Run the [drills](../../deploy/drills/README.md) on the target host before a release.

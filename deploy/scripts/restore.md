# Restore DocuHive without overwriting the live archive

Restore into a new host or fresh directories and an empty database. Keep the current
vault and database untouched until the restored instance passes its checks. Use the image
versions that produced the backup; upgrade only after that instance is healthy.

## Full recovery

1. Recover the private env file, overlay, mail encryption key, restic password and target
   credentials from their independent secret backup. Install the pinned restic version and
   Docker. Recreate the host user/directories from the [operations guide](../../docs/setup/operations.md).
2. Run `restic -r <repository> snapshots --tag docuhive`. Choose one snapshot, then
   `restic -r <repository> restore <snapshot-id> --target /srv/docuhive-recovery`.
   Do not restore `latest` onto the existing mount. Restic restores the absolute source paths
   underneath the target directory; locate the restored `vault` **and** `staging` trees there.
3. Find the custom-format dump in the restored vault's `_system/db`. Copy the restored vault
   and staging into the new installation's corresponding storage locations, retaining their
   ownership. Keep the original `_system/VAULT_ID`; do not initialise a new vault over it.
4. Use the matching backup-era images and the new env file. Start **only PostgreSQL** with
   `docker compose --env-file <recovery.env> -f deploy/compose.yml up -d --wait postgres`.
   On a fresh DB, restore with:

   ```sh
   docker compose --env-file <recovery.env> -f deploy/compose.yml exec -T postgres \
     pg_restore -U docuhive -d docuhive --exit-on-error --no-owner --no-privileges \
     < /path/to/restored.dump
   ```

5. Run `db current` using the backup-era backend image. Start API and workers with the
   matching env file; current-release startup runs migrations before serving.
6. Verify the vault ID matches `settings['vault.id']`, sign in, inspect several PDFs and
   metadata, search, and let staged jobs resume. Run the read-only full vault health check.
   When a reference snapshot is available, run `make verify-restore ORIGINAL=… RESTORED=…`
   to compare every document byte and metadata file without publishing names.
7. After verification, switch the private HTTPS endpoint and re-enable the backup timer.
   Keep the old installation isolated until the restored one has its own successful backup.

A fresh database restore preserves sessions, users, metadata locks, mail cursors and jobs.
Keep the original mail-token encryption key or reconnect the accounts. Staging is part of
the same quiesced snapshot; restore it before running workers so accepted input is not lost.

## Database-only recovery

Use the dump matching the current vault/staging snapshot. Restore to an **empty, disposable
PostgreSQL instance** using step 4. Validate counts, document metadata and search, then plan
the cutover. A newer vault with an older DB can contain orphan folders; do not delete them.
Do not use `pg_restore --clean` against the live database.

## One-document recovery

Restore a snapshot to a temporary directory. Locate the document's immutable vault folder
and compare its original checksum and `meta.json` with the read-only health report. Recover
missing files to the expected original location only while writers are stopped and after
backing up the damaged state. Existing files must not be overwritten silently. A document
absent from the DB needs the document core's rebuild/import capability; do not manufacture
rows by hand or claim DB rebuilding from a file copy.

## Rebuild without a database dump

Use a restored copy of the vault and a fresh database: `docuhive db upgrade`, then
`docuhive vault init` (it binds the existing `VAULT_ID`), then `docuhive vault rebuild`; a
`--dry-run` first only validates the `meta.json` files. See the [rebuild drill](../drills/rebuild.md).
Users, sessions, tokens, mail credentials and chat history are not in the vault and still
need a database dump.

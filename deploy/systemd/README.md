# `deploy/systemd`

**Overview.** Host units for consistent backups. What is backed up, on which days and at what
time is chosen in the app (Storage health → Backup); these units only ask regularly whether a
backup is due. Install them explicitly after a successful manual run.

## What's here

| Path | What it is |
| --- | --- |
| [docuhive-backup.service](docuhive-backup.service) | Runs the backup as the dedicated host user with a private environment file |
| [docuhive-backup.timer](docuhive-backup.timer) | Asks every 15 minutes whether a backup is due by the app's schedule; catches up after the host was off |
| [docuhive-backup.path](docuhive-backup.path) | Starts a backup at once when **Back up now** is pressed in the app |

## Extending

Adjust mount dependencies and writable paths for the actual backup target. Follow the
[operations guide](../../docs/setup/operations.md); do not put secrets in a unit file.

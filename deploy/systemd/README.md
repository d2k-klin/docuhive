# `deploy/systemd`

**Overview.** Host timer for consistent nightly backups; these units are installed explicitly
by the administrator after a successful manual run.

## What's here

| Path | What it is |
| --- | --- |
| [docuhive-backup.service](docuhive-backup.service) | Runs the backup as the dedicated host user with a private environment file |
| [docuhive-backup.timer](docuhive-backup.timer) | Schedules 03:00 local time with missed-run recovery |

## Extending

Adjust mount dependencies and writable paths for the actual backup target. Follow the
[operations guide](../../docs/setup/operations.md); do not put secrets in a unit file.

# `deploy/drills`

**Overview.** Recovery rehearsals for an isolated copy of DocuHive. Use synthetic files first,
then repeat on the target hardware and retain the aggregate evidence outside private data.

## What's here

| Path | What it is |
| --- | --- |
| [nas-down.md](nas-down.md) | Disconnect storage, verify staged input survives and recover |
| [restore-db.md](restore-db.md) | Restore the quiesced database/file snapshot to a disposable instance |
| [host-loss.md](host-loss.md) | Recover onto a clean host using the runbooks only |
| [rebuild.md](rebuild.md) | Rebuild document metadata from a restored vault when core rebuild is available |
| [verify_snapshot.py](verify_snapshot.py) | Compare document bytes and metadata between two vault snapshots |

## Extending

Never run destructive drills against the only copy. Record date, hardware, image tags,
snapshot IDs, elapsed time and pass/fail; keep document names and credentials private.

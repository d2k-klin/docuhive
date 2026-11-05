# Vault-only rebuild drill

Prerequisite: a verified source snapshot. `docuhive vault rebuild` is part of the document core.

Restore a restic snapshot into a separate vault, create an empty disposable database and
register the restored vault ID. Run the core rebuild twice. Compare document counts and
all persisted metadata with the original reference, then compare every file with
`make verify-restore ORIGINAL=… RESTORED=…`. Rebuild must be repeatable; original folders
must not move, and restricted documents must retain their privacy policy when re-indexed.

A vault-only rebuild cannot restore users' password hashes, sessions, mail cursors, chat
history or token secrets. Use the database dump for full recovery. It passed locally with synthetic
files on 2026-11-05 ([report](../../docs/Developer-QA/reports/local-production-validation-2026-11-05.md));
record it as pending until it has passed on the target storage too.

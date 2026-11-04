# Vault-only rebuild drill

Prerequisite: the document-core implementation supplies `docuhive vault rebuild` and a
verified source snapshot. This command is not implemented by the capture/operations phases.

Restore a restic snapshot into a separate vault, create an empty disposable database and
register the restored vault ID. Run the core rebuild twice. Compare document counts and
all persisted metadata with the original reference, then compare every file with
`make verify-restore ORIGINAL=… RESTORED=…`. Rebuild must be repeatable; original folders
must not move, and restricted documents must retain their privacy policy when re-indexed.

A vault-only rebuild cannot restore users' password hashes, sessions, mail cursors, chat
history or token secrets. Use the database dump for full recovery. Record this drill as
pending until real core rebuild and target storage have actually passed it.

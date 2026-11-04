# Backup and restore drill

1. In an isolated deployment, seed synthetic documents with manual metadata, facts, private
   and shared ownership. Keep one pending staged document too.
2. Run the real backup script into a temporary restic repository. Confirm the status file
   reports success and writers restart. Stop the disposable source writers before comparing.
3. Follow the [restore runbook](../scripts/restore.md) into new paths and an empty database.
4. Compare database row counts and metadata locks, facts, users and token scopes; verify the
   staged input resumes, sign-in works and ten fixed search queries still find the same docs.
5. Run `make verify-restore ORIGINAL=<reference-vault> RESTORED=<restored-vault>`. It checks
   every document file, not just twenty samples; library links and transient system state
   are excluded. A mismatched file or empty reference must fail the check.
6. Record image versions, snapshot, elapsed time and results. Repeat on the actual host/NAS;
   mocked orchestration and a schema-only upgrade are separate evidence.

# NAS-offline drill

Use a disposable deployment and synthetic files. Confirm a recoverable backup first.

1. Record the vault ID, document count and input checksums. Save a three-page phone capture
   and one scanner file. Disconnect the test NAS share for ten minutes.
2. Submit another upload. Once core intake is integrated, it must be accepted into SSD
   staging and remain staged/deferred while the NAS is unavailable. Capture shows queued
   if API writers are unavailable. The archive banner must report unavailable storage.
3. Confirm scanner inputs are untouched; library sync creates nothing. A backup must fail
   before dumping or writing status into the bare mount point. Inspect that bare mount
   directory from the host without creating any file inside it.
4. Reconnect the NAS. Verify the same vault ID, restart workers if a hard NFS call is still
   blocked, and wait for all staged documents to become stored. Verify PDF pages, original
   checksums, search, no duplicate rows and release of scanner inputs only after verification.
5. Record outage/recovery time and every failure. A missing marker, wrong marker and
   read-only mounted share should also fail safely. Do not mark the NAS gate passed from
   a renamed directory or mocked storage result alone.

# Local production validation — 2026-11-05

Candidate: v0.3.1 (`a01d837`) plus the fixes in this report. Environment: development Mac,
Docker Desktop with 2 CPUs and 2 GB, the production images built from `deploy/compose.yml`,
synthetic documents and test accounts only. This is evidence for the checks that need no
owner input. It does not sign any target-host, NAS, phone, real-provider or real-mailbox gate.

## What ran

| Check | How | Result |
| --- | --- | --- |
| Lint and types | ruff, mypy, eslint, tsc | Pass |
| Licences and advisories | Python licence gate, `pip-audit`, `npm audit --omit=dev` | Pass, no known vulnerabilities. The npm `license-checker` errors locally ("No packages found") and is verified in CI only |
| Unit tests | `pytest -m "not integration"`, vitest | 389 passed, 87.14% lines; 8 web tests passed |
| Integration tests | `pytest -m "integration and not system"` against PostgreSQL | 68 passed |
| QA offline checks | `make qa-check` (system and contract tests) | 70 passed, 1 expected failure |
| Import boundaries | `make qa-boundaries` | 1 contract broken, [QA-004](../bugs.md#qa-004), unchanged and still open |
| Installation guide | Every step of `docs/setup/installation.md` on the production images | Pass (see below) |
| End to end | Sign-in, upload, OCR, search, downloads, sharing, trash, setup checklist through the web app | Pass |
| Ingest time, German and English OCR | Image-only A4 scans at 300 dpi, `deu+eng`, inside the production worker | 1 page 4.6 s, 5 pages 12.8 s (target 60 s) |
| OWASP ZAP baseline | ZAP stable, signed out and signed in as a household member | 0 failures; warnings recorded in the [security checklist](../../security-checklist.md) |
| Backup and restore | `deploy/scripts/backup.sh` with restic 0.18.1, restore into fresh folders and an empty database | Pass |
| Vault-only rebuild | `vault init` and `vault rebuild` twice on a restored copy, empty database | Pass |
| Storage unavailable | Missing and wrong `_system/VAULT_ID` | Pass |
| Worker killed mid-document | `docker kill` of `worker-ocr` during a 5-page scan, then restart, three times | Failed before the fix (stuck for the 30-minute lease); passes after it, stored 9 s after each kill |

## Installation guide

The steps were followed in order, with these local substitutions:

- **`make`** is blocked by an unaccepted Xcode licence on this Mac, so its underlying `docker compose` commands were run instead.
- **Storage paths:** the PostgreSQL data folder is a Docker volume, because Docker Desktop bind mounts cannot be owned by UID 999.
- **Address:** the web app was published on `127.0.0.1:3300`, because another dev server held port 3000. The public URL was plain HTTP, so the `Secure` session cookie was sent by hand.

None of these affects a Linux host.

- **Step 4:** `run --rm --no-deps api mail gen-key` printed the bare key on stdout and logs on stderr, as the guide says. Both keys reached `api`, `migrate`, `worker` and `worker-ocr` through `app.env`, and not `web`. `DOCUHIVE_ENV` stayed `prod`.
- **Step 5:** `user create` (admin and member) and `vault init` worked through `run --rm api`.
- **Step 6:** only the web app was published, on loopback.
- **Setup checklist:** every check rendered, and every `help_doc` exists. `mail.key` showed `ok` from `app.env`.

## End to end

- A German and English scan was stored, then found by "Stromlieferung" and by the inflected "Rechnungen". The original and the archive PDF both downloaded.
- **Sharing:**
  - a member read a shared document and could not edit it (404);
  - once the owner made the document private, the member could not read it (404) and did not see it in their list.
- **Refusals:** a byte-identical upload was reported as a duplicate. Empty files and unsupported types were refused at submission with 415, as the user guide says.
- **Trash:** a trashed document disappeared from search and came back on restore.

## Backup, restore and rebuild

- **Backup:** `backup.sh` stopped `api`, `worker` and `worker-ocr`, wrote and checked the dump, backed up the vault and staging, and restarted the writers. It wrote `ok` to `backup-status.json`. restic ran from its official 0.18.1 image, with identical paths.
- **Restore** of that snapshot into a fresh folder:
  - `verify_snapshot.py` found 21 files with identical bytes and metadata;
  - `VAULT_ID` was kept and `library/` was excluded.

  restic exited 1 only because it couldn't change file ownership on the Docker Desktop shared folder.
- **Database:** `pg_restore` of the dump into an empty PostgreSQL gave the same document count, user count and `vault.id` as the live database.
- **Rebuild:** `vault rebuild` into an empty database, run twice, gave the same rows. Id, title, category, owner, sharing, checksum, status, pages, date, manual fields and trash state hashed identically to the live database, and the vault was byte-identical afterwards. As the drill says, users, sessions and tokens are not in the vault.

## Storage unavailable

With the marker missing, and then a wrong one:

- the dashboard reported storage as unavailable;
- uploads were accepted and stayed staged;
- `backup.sh` refused, writing no snapshot and no status;
- nothing was created in the vault folder.

Once the marker was restored, both staged documents were stored. The missing-marker refusal printed a traceback; it now exits with "Mount the registered vault before backing up".

This is a local pre-check only. The [NAS drill](../../../deploy/drills/nas-down.md) itself needs the real share.

## Worker killed mid-document

**Before the fix:** after `docker kill` and a restart, the document stayed in processing for over 400 s. The job's lease is 30 minutes (`ingest.process` `timeout_s=1800`), and only lease expiry released it. Nothing was duplicated, and it would have finished after the lease, but a scan showing as processing for half an hour is not an acceptable recovery.

**Fix:** at start-up, before claiming anything, a worker releases running jobs whose lease names this host and either its own PID or a PID that no longer exists. A restarted container keeps its hostname and usually its PID. A live sibling process on the same host is left alone. `test_restarted_worker_releases_only_dead_processes_jobs` covers the predecessor, dead, live and other-host cases.

**After the fix:** the worker was killed three times, at different points in a 5-page scan. Each time the restarted worker logged "Released 1 jobs left by a stopped worker on this host", and the document was stored 9 s after the kill, with no duplicate rows.

A job whose container was *recreated* rather than restarted, for example by an image change, still waits for its lease: the new container has a new hostname. This is deliberate. Pinning a fixed `hostname:` would let a scaled-out sibling with the same in-container PID have its live job released.

## Findings fixed with this report

- The calendar feed, the only route taking a token in its URL, accepted `read`, `write` and `admin` tokens. Calendar services store that URL and may log it. The feed now needs a new `calendar` scope, which every other route refuses.
- `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy` are now `same-origin`.
- Worker restart recovery, above.
- `backup.sh` refuses a missing vault marker cleanly.
- Stale runbook lines said `vault rebuild` was not available.
- The Trash page said an administrator can remove documents for good, which isn't possible yet.

## Left to the owner

- **[QA-004](../bugs.md#qa-004):** four intelligence modules read `public_url`, `vault_dir` and `defaults_dir` from the platform's private settings. The agreed config contract has no such accessor, so the owners must add one or remove the reads.
- **Real providers:** Ollama or cloud keys, and the Gmail and Outlook app registrations.
- **Target hardware:**
  - every target-host check: timings, the ZAP scan over HTTPS, `ss -tlnp`, and three nightly backups;
  - the NAS outage drill;
  - phone acceptance;
  - host-loss recovery.
- **Real-document OCR measurements:** the [OCR gate](../../decisions/0001-ocr-gate.md).

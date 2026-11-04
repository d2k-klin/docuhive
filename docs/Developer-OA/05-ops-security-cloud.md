# OA-05 — Ops, resilience, hardening, cloud (OA-M7, OA-M8)

## OA-M7 — Ops: compose, NAS, backups, drills, library view

**Goal:** running for real on the always-on host with the WD NAS, surviving failures (STO-03/05/08, NFR-03).

### 7.1 Production compose — `deploy/compose.yml` (+ `compose.local.yml`)
| Service | Image | Notes |
|---------|-------|-------|
| `postgres` | `pgvector/pgvector:pg16` | volume on the **host SSD** (`/srv/docuhive/pg`). Healthcheck `pg_isready`. Not published (internal network only) |
| `gotenberg` | `gotenberg/gotenberg:8` | internal only. `--api-timeout=120s`, `--chromium-deny-list` (OA-M1), `--libreoffice-auto-start=true` |
| `api` | the docuhive image | `docuhive api`. Depends on postgres being healthy. Read-only rootfs + tmpfs `/tmp`. Mounts: vault (rw), staging (rw), overlay (ro) |
| `worker-ocr` | the docuhive image | `docuhive worker --queues ocr --concurrency 1`. CPU limit configurable |
| `worker` | the docuhive image | `docuhive worker --queues ai,mail,default --concurrency 4` |
| `web` | `apps/web` image (Next standalone output) | `DOCUHIVE_API_URL=http://api:8000`. Published on the LAN/Tailscale IP only (`${BIND_IP}:3000`) |
| `migrate` | the docuhive image | one-shot `docuhive db upgrade`. api/worker depend on it completing successfully |

- Everything runs as uid 1000, and `security_opt: no-new-privileges`.
- CL adds `ollama` and anything AI-specific in `deploy/compose.ai.yml`.
- **Run command:** `docker compose -f deploy/compose.yml -f deploy/compose.ai.yml -f overlay/compose.override.yml up -d`, wrapped as `make up`.
- **Images:** built in CI and pushed to GHCR (`ghcr.io/<owner>/docuhive`, `docuhive-web`), tagged with the git SHA and semver on release.

### 7.2 NAS setup — `docs/setup/nas-wd-ex2-ultra.md`
A step-by-step guide (from Q3):
1. Back up the NAS first. Update to the latest My Cloud OS 5 firmware (one-way; note the RAID-reset anecdote).
2. Check the drive health (SMART) and whether RAID 1 is active.
3. **Disable** the cloud access/remote features, UPnP/port forwarding, and any unused services (FTP, DLNA). Change the admin password.
4. Create a share `docuhive` and a user `docuhive`. Give that user read/write on the share; other users get no access, or read-only if wanted for the `library/` view.
5. **Enable NFS** for the share, restricted to the host's IP (`rw,sync,no_subtree_check`, `all_squash` mapped to uid 1000 if possible). Fall back to SMB3 if NFS on this model is unreliable.
6. Host mount: a systemd automount unit (example below), plus `docuhive vault init`.
7. **End-of-support note:** WD support for this model ends Dec 2026. Keep it LAN-only. Migrating later is: copy the vault folder, then change `VAULT_DIR`.

```ini
# /etc/systemd/system/srv-docuhive-vault.mount
[Unit]
Description=DocuHive vault on WD NAS
After=network-online.target
Wants=network-online.target
[Mount]
What=wdnas.local:/nfs/docuhive
Where=/srv/docuhive/vault
Type=nfs
Options=vers=3,hard,timeo=600,retrans=2,_netdev,noatime
[Install]
WantedBy=multi-user.target
# + srv-docuhive-vault.automount with [Automount] Where=/srv/docuhive/vault, TimeoutIdleSec=0
```
The `hard` mount option means writes block, rather than fail silently, during a NAS outage. The vault-ID check (OA-M3) covers the "not mounted at all" case.

### 7.3 Backups — `deploy/scripts/backup.sh` + systemd timer (nightly 03:00)
1. `pg_dump -Fc` of the docuhive DB → `vault/_system/db/docuhive-<date>.dump`. Keep 14 dumps.
2. `restic backup /srv/docuhive/vault --exclude vault/library` to every target in `RESTIC_REPOSITORIES` (e.g. a USB disk `/mnt/usb-backup/restic` and/or `b2:bucket:docuhive`). The password comes from the `RESTIC_PASSWORD_FILE` file (mode 600).
3. `restic forget --keep-daily 7 --keep-weekly 8 --keep-monthly 24 --prune` (weekly).
4. `restic check --read-data-subset=5%` (monthly).
5. Write the result to `vault/_system/backup-status.json` (`{at, ok, targets: [...], error}`). The dashboard shows a warning if the last success is older than 48 h (served via `/api/system/stats`).

Restore runbook `deploy/scripts/restore.md`: full restore to a new host, single-document restore from restic, and DB-only restore.

### 7.4 Drills — `deploy/drills/` (scripts + expected results; run before v1, then monthly)
| Drill | Steps | Pass |
|-------|-------|------|
| `rebuild.sh` | throwaway compose project → `vault rebuild` from a restic snapshot | counts + 20 random documents' metadata equal to prod |
| `nas-down.md` | stop NFS on the NAS for 10 min while uploading | uploads staged, the banner shows, everything stored after recovery, no file in a bare mount point |
| `restore-db.md` | restore the latest dump into a new DB | app starts, search works |
| `host-loss.md` | new host from scratch using the docs only | running within 2 h |

### 7.5 Library view (STO-03) — `docuhive/vault/library.py`
- `@periodic("library.sync", every=1h)`, plus an on-demand `docuhive vault library-sync`.
- Path: `library/<category id with "/" as folders>/<YYYY of document_date or added_at>/<YYYY-MM-DD> <title>.pdf`. The title is sanitised: `/\:*?"<>|` and control characters removed, max 120 chars, NFC-normalised. Collisions get ` (2)`. Uncategorised documents go to `library/_uncategorized/`.
- **Hardlink** `archive.pdf` into the library (`os.link`). If the filesystem refuses (`EXDEV`/`EPERM`, e.g. on SMB), log once and disable the library feature (`settings['library:disabled']`). Never copy, because copies would double the storage use.
- **Sync algorithm:**
  1. Build the desired path set from the DB.
  2. Walk `library/`.
  3. Remove links that are not desired; create the missing ones.
  4. Remove empty directories.
- Owner-private documents go under `library/_private/<username>/…`; shared ones go at the top level.
  <br>`ponytail:` share-level ACLs on the NAS are the admin's job; the docs explain it.

### Acceptance (OA-M7)
- Production stack running on the host with the NAS vault.
- All four drills pass and their results are recorded in `docs/decisions/0002-drills-<date>.md`.
- A backup has run for 3 consecutive nights.

---

## OA-M8 — Hardening + cloud profile

### 8.1 Security checklist (NFR-02) — `docs/security-checklist.md`, every box ticked
- [ ] **Dependencies:** `pip-audit` and `npm audit --omit=dev` in CI (fail on high), plus weekly Dependabot.
- [ ] **Licences:** CI licence check passing. `THIRD_PARTY.md` generated, listing the subprocess tools (Ghostscript, unpaper) and their licences.
- [ ] **Secrets:** gitleaks in pre-commit and CI. `.env` mode 600. No secrets in logs (a redaction filter for `password`, `token`, `secret` and `authorization` keys).
- [ ] **Uploads:** magic-byte checks. The size limit is enforced while streaming. The decompression bomb guard (`MAX_IMAGE_PIXELS`) and the page cap are set. Gotenberg is internal-only with external URLs denied. OCR runs in separate processes with timeouts.
- [ ] **Fuzz corpus** `tests/fixtures/malicious/`: zip-bomb docx, a PDF with JS, a PDF with an infinite xref loop, a polyglot JPEG/HTML, a 50k×50k PNG, an `.eml` with a remote-image beacon, HTML with `<script>`/`<iframe>`. Each is either quarantined or rendered inert, and the worker never crashes.
- [ ] **Web headers:** a CSP in Next middleware (`default-src 'self'; frame-src 'self'; img-src 'self' data: blob:; object-src 'none'; base-uri 'none'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, and `Permissions-Policy: camera=(self)`.
- [ ] **Downloads:** `Content-Disposition` with an RFC 5987 filename. Originals are always `attachment` unless they are PDF/image. HTML originals are never rendered inline.
- [ ] **Auth:** session fixation (new token on login), logout everywhere, rate limits verified, CSRF header verified, cookie flags correct behind Tailscale HTTPS.
- [ ] **Containers:** non-root, read-only rootfs (api/web), no Docker socket mounts, internal network for postgres and gotenberg.
- [ ] **Permission matrix test** green, and CL's privacy tests green (cross-check with CL).
- [ ] **Network:** no service bound to `0.0.0.0` on the host except via Tailscale/LAN. Document how to check with `ss -tlnp`.

### 8.2 Cloud profile — `deploy/compose.cloud.yml` + `docs/setup/cloud.md`
- The same services. No `ollama`, because CL's routing defaults switch to cloud providers through the `routing.cloud.yaml` example. The `worker-ocr` concurrency is sized to the vCPUs.
- **Vault:** an attached block volume mounted at `/srv/docuhive/vault` (Hetzner Volume, EBS or a Lightsail disk).
- **Access**, two documented options:
  - **A (recommended):** Tailscale on the VM, nothing public.
  - **B:** a `caddy` service with automatic TLS for `docs.example.com`, plus a `fail2ban` jail on login failures (log format documented), with the API never exposed directly.
- **WD as the permanent home copy:** `deploy/scripts/pull-to-nas.sh`, run on a home device (the always-on host, or any Linux box/Raspberry Pi on the LAN).
  - It runs `restic restore latest --target /mnt/wd/docuhive-mirror` from the cloud's B2/S3 restic repo, or `rclone sync` over Tailscale SFTP from the VM.
  - Scheduled nightly, writing `mirror-status.json`.
  - Because the vault is self-describing, the mirror is a complete archive on its own.
- Sizing table:
  - **Small (personal):** 4 vCPU, 8 GB, 100 GB volume.
  - **Comfortable:** 4–8 vCPU, 16 GB.
  - Include rough monthly cost ranges, labelled "check current pricing".
- **AWS scale-out notes** (not built, documented only): ECS Fargate (web, api, worker, worker-ocr), RDS Postgres with pgvector, EFS for the vault, Bedrock for AI, an ALB, and Secrets Manager. List what would need to change: nothing in code, except an S3 vault backend if EFS cost or latency is a problem.

### 8.3 Release
- `CHANGELOG.md`, semver, and a GitHub Release workflow building the images. A `v1.0.0` tag once the J5 acceptance passes.
- An upgrade guide: `docker compose pull && just up`. `migrate` runs automatically, and `meta.json` migrations run via `docuhive vault migrate` if the release notes say so.

### Acceptance (OA-M8)
- The security checklist is complete. The fuzz corpus passes.
- A fresh cloud VM is deployed by following `docs/setup/cloud.md` alone, and `pull-to-nas.sh` mirrors it to the WD.
- **J5** acceptance, run jointly with CL: every requirement ID verified in `docs/decisions/0003-v1-acceptance.md`.

# Security checklist

The NFR-02 hardening checklist from [OA-M8](Developer-OA/05-ops-security-cloud.md#81-security-checklist-nfr-02--docssecurity-checklistmd-every-box-ticked), with the evidence for each item. Last checked 2026-11-04.

- [x] **Dependencies.** CI runs `pip-audit` and `npm audit --omit=dev --audit-level=high` ([ci.yml](../.github/workflows/ci.yml)). Dependabot runs weekly for uv, npm and GitHub Actions ([dependabot.yml](../.github/dependabot.yml)).
- [x] **Licences.** CI runs `deploy/scripts/check_licenses.py` and `license-checker`. [THIRD_PARTY.md](../THIRD_PARTY.md) lists Ghostscript and unpaper as separate subprocesses.
- [x] **Secrets.**
  - gitleaks runs in pre-commit and in CI.
  - The production `.env.production` is mode 600 ([operations guide](setup/operations.md)).
  - Every log handler (worker, API and uvicorn's own) masks values after `password`, `token`, `secret`, `authorization`, `api_key`, `session` and `cookie` keys (`docuhive.cli.Redact`, tested in `test_cli.py`). Tracebacks are not scrubbed.
- [x] **Uploads.**
  - The file type is detected from its content (magic bytes), not its name (`ingest/detect.py`).
  - The size limit is enforced while the upload streams in (`UploadLimitMiddleware`, `api/upload.py`).
  - Limits: `MAX_IMAGE_PIXELS` 200 M, a 500-page cap, and zip expansion limits.
  - Gotenberg is on the internal network only, and its Chromium, LibreOffice and download-from deny lists block external URLs ([compose.yml](../deploy/compose.yml)).
  - OCR and conversion steps run in separate processes with timeouts (`ingest/safety.py`).
- [x] **Fuzz corpus.** `tests/core/test_malicious_integration.py` generates the corpus at test time, so the public repository holds no weaponised files. It runs each file through the real pipeline:

  | File | Outcome |
  |---|---|
  | Zip-bomb docx | refused at submission |
  | PDF with JavaScript | stored, no JavaScript in the archive |
  | PDF with an infinite xref loop | stored |
  | JPEG/HTML polyglot | stored as an image |
  | 50k×50k PNG | quarantined |
  | `.eml` with a remote-image beacon | stored, no remote URL in the archive |
  | HTML with `<script>`/`<iframe>` | stored, no script or remote URL in the archive |

  The worker never crashes.
- [x] **Web headers.** [next.config.ts](../apps/web/next.config.ts) sets the CSP (`default-src 'self'; frame-src 'self'; img-src 'self' data: blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`), `nosniff`, `Referrer-Policy: same-origin` and `Permissions-Policy: camera=(self)`. The file route alone allows framing by DocuHive's own pages, for the PDF preview. Known limit: `script-src` allows `'unsafe-inline'`, because Next.js needs nonces to remove it.
- [x] **Downloads.**
  - Starlette's `FileResponse` writes an RFC 5987 `filename*`.
  - Originals are sent as attachments unless they are PDF or images (`INLINE_ORIGINALS`), so HTML originals are never rendered inline.
  - The preview shows the archive PDF, which has no JavaScript.
- [x] **Auth.**
  - Every login issues a new session token, and only its hash is stored.
  - `logout-everywhere` exists; a password change also ends every session and revokes all tokens.
  - Login rate limit and the CSRF header are covered by `test_auth_integration.py`.
  - The cookie is `HttpOnly`, `SameSite=Lax`, and `Secure` outside development.
- [x] **Containers.** All are non-root with read-only root filesystems (writable volumes and tmpfs where needed), use `no-new-privileges`, and drop all Linux capabilities. There are no Docker socket mounts. PostgreSQL and Gotenberg are on an internal-only network.
- [x] **Permission matrix.** `tests/core/test_permission_matrix_integration.py` walks every route in the OpenAPI schema:
  - Without a session, everything answers 401. The only exceptions are login, the health check and the token-authenticated calendar feed.
  - Every document route refuses another user, administrators included, on a private document.

  CL's privacy tests (`tests/intel/test_privacy_audit.py`) pass.
- [x] **Network.** Only the web app publishes a port, on `127.0.0.1:3000`. The operations guide shows how to check this with `ss -tlnp`.

## Still open

- An OWASP ZAP baseline scan of the running web app (QA release gate).
- The checks on the target host itself: `ss -tlnp`, and file modes on the real `.env.production`.

# Capture and operations verification

Date: 2026-11-04 · Decision: code ready for integration; hardware acceptance pending.

The capture and operations phases now have executable implementations and runbooks.
This records local evidence separately from the production-release gate.

## Verified locally

- A digest-pinned production backend and standalone web image were built. The disposable
  stack ran API, both workers, PostgreSQL, Gotenberg and web. The app containers were UID
  1000 with read-only roots; PostgreSQL UID 999 and Gotenberg UID 1001 also ran non-root.
  Only web had a host port, bound to loopback. An ingress network is required in addition
  to the internal network for that published loopback port to work.
- A real restic 0.18.1 binary was downloaded from its release and SHA-256 verified in a
  temporary directory. The actual backup script stopped writers, validated a custom-format
  database dump, backed up the vault and staging, and restarted writers successfully.
- A restic snapshot was restored into a fresh directory. All three synthetic document files
  matched byte-for-byte, including metadata, and the pending staged file matched too.
  The dump restored into an empty PostgreSQL database with document title/manual locks,
  money facts/currency and owner records preserved. This is synthetic local recovery.
- The v0.1.0 schema (core 0001, intelligence 0008) upgraded to the current head twice without
  losing document metadata, facts, password hashes or token scopes. Three additional real
  PostgreSQL checks covered scanner retention/rejection and library hardlinks, including
  recovery after a lost manifest. These four integration checks passed on a separate DB.
- The network-free suite passed **357 tests**, with **59 integration tests deselected**,
  **1 expected failure** and **87.44% overall coverage**. Ruff, formatting, mypy and ShellCheck
  passed. Web logic passed **8 tests**; TypeScript/ESLint and the final source production build
  passed. Existing shell/control-height browser checks passed **12 tests**.
- Production browser checks passed the six viewport/theme combinations (375/768/1280,
  light/dark) for layout/accessibility, durable queue concurrency, offline reload/reconnect
  photo rotation/reordering/combined multipart upload, account isolation and retained rejected
  bytes: **30 passed**. Screenshots were
  inspected. These responses use synthetic API fixtures, not a functioning archive backend.

The backend image rebuilt and passed real OCR (PDF/A-2, no expected words missing) as UID
1000 with a read-only root and network disabled. A final web image rebuild stalled while
resolving the pinned Docker base and was stopped; final source was built and all thirty
capture checks passed against that local production build. The initial standalone image
and production stack had already built and run successfully. No image was published.

## Boundaries of the evidence

The local Docker host is macOS/Colima. The PostgreSQL check used a UID-owned tmpfs because
macOS bind-mount ownership cannot model a Linux SSD data directory. Production's bind mount
and the NAS propagation/mount behaviour still need the Linux target-host drill.

In this checkout, `ingest.submit` and the document-service implementation are still contract
stubs; phase 1 is being built separately. The adapters use those contracts and fail honestly
while unavailable. Repeat the stored/searchable-document journeys after integration.
The database restore above proves records and files survive, not complete end-to-end use.

## Pending release evidence

- Physical iPhone/Android installation, EXIF/camera behaviour and away-from-home Tailscale capture.
- Actual scanner/SMB/NFS semantics, NAS outage and recovery, and share ACLs for private library links.
- Three consecutive successful nightly backups and the timer on the real Linux host.
- Complete host-loss and vault-only rebuild drills; `vault rebuild` remains a document-core dependency.
- Real provider/mailbox runs, OCR/performance calibration and the QA release gate.

No production data was used, no target deployment was changed and no release gate is marked GO.

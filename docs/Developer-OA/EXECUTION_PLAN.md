# Developer OA — Execution plan

**Overview.** Implement the OA track in dependency order using the binding shared contracts.
Developer CL's documents and implementation paths remain outside this work.

## Work sequence

1. **OA-M0:** establish the Python and web workspaces, exact contract models and stubs,
   health endpoint, command line, development containers, CI and contributor instructions.
2. **OA-M2:** implement validated settings, overlay loading, isolated migration environments,
   the core schema, transactional sessions, durable jobs, worker, scheduler and contract fakes.
3. **OA-M1:** implement isolated conversion/OCR primitives, a reproducible spike command,
   synthetic fixtures and character error measurement. Record measured results separately
   from the private-corpus gate.
4. **Gate:** evaluate 50 private documents and ten transcribed pages on the target host.
   A GO permits OA-M3; a NO-GO selects the Paperless adapter. Neither result is assumed.
5. **OA-M3:** implement the selected ingest backend, vault, document service and event delivery.
6. **OA-M4–M6:** implement permissions, authentication, API/search, web workflows and capture.
7. **OA-M7–M8:** deploy, back up, restore, harden and validate the cloud profile.

## Verification

- Run contract and unit tests without credentials or network access.
- Run formatting, lint, typing, documentation links and web build checks.
- Exercise PostgreSQL migrations, queue concurrency, scheduler leadership and lease recovery
  against a disposable Compose database when Docker access is available.
- Record unavailable external acceptance checks honestly: private OCR corpus, target-host
  timing, NAS, actual phones, three nightly backups, cloud VM and CL's joint acceptance.
- Update [STATUS.md](STATUS.md) after each deliverable; never mark a gate passed from mocks.

## Decisions and constraints

- `make` is canonical, following the project `repo-structure` skill. The earlier planning
  references to `just` translate to the identically named Make targets; no justfile is added.
- Ruff checks and formats Python. Markdown and its binding contract snippets are preserved;
  documentation links and contract drift have separate tests.
- Use the proposed Apache-2.0 licence and Python 3.12. Use patched Next.js 16.4.5
  for the new workspace: the specified Next.js 15 line retains a vulnerable PostCSS
  dependency in the current audit. The App Router and shared API contracts stay the same.
- Existing planning edits are preserved. No commits, releases or production deployments are
  implied by local implementation.
- The user confirmed on 2026-11-03 that no private OCR corpus or reference transcriptions
  are currently available. The OA-M1 decision therefore remains pending.

## Extending

Continue with the next incomplete milestone in STATUS.md. Keep interface changes additive
and update the shared contracts alongside any additive model changes.

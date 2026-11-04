# Changelog

Changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and SemVer.

## [Unreleased]

### Changed

- TypeScript 7 for the web app's typecheck and build, ocrmypdf 17, uvicorn 0.54 and psycopg 3.3.
- The worker image moves to Debian trixie (Ghostscript 10.05).

### Fixed

- OCR in the container: ocrmypdf refused the bookworm image's Ghostscript 10.0.0 whenever existing text was skipped, so every scan failed.

## [0.1.0] - 2026-11-04

### Added

- Binding contract models, Python and web workspaces, CLI and health API.
- Validated core settings, private overlay merging, prompt versions and plugin hooks.
- Independent database migration environments and the core PostgreSQL schema.
- Durable jobs, retries, lease recovery, scheduler leadership and reusable platform fakes.
- Session and token authentication with CSRF checks and centralized document permissions.
- Isolated OCR spike, safe content detection, conversion, text extraction, previews and CER measurement.
- Streaming API proxy and generated TypeScript API types.
- Developer commands, disposable test stack, CI and contributor documentation.
- Mr.D brand assets with a manifest check, and a README in every folder describing each file.
- Real light and dark screenshots of the app, captured from the synthetic QA environment.

### Changed

- GitHub Actions (checkout, setup-node, setup-python, upload-artifact) move to v7; ESLint 10, lucide-react 1.x, openapi-fetch 0.17 and current Python dev tools.
- Dependabot updates Python through `uv`, so `uv.lock` stays in sync; Tailwind and `@types/node` majors are done by hand.
- The README follows the Hive project template: Mr.D hero, what DocuHive does, what you'll learn, quick start, documentation, honest project status.
- The documentation index is organised by Using, Understanding, Learning, Extending and Planning, and the link check covers every README.

### Security

- Select a patched Next.js release and current test tooling for the new web workspace.
- Record the unmeasured OCR gate explicitly; the archive backend remains unselected.

[Unreleased]: https://github.com/d2k-klin/docuhive/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/d2k-klin/docuhive/releases/tag/v0.1.0

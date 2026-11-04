# Contributing to DocuHive

Use Python 3.12, Node 22.12+ and Docker Compose. Install `uv`, `make`, `gitleaks`
and a current Node/npm before starting.

```sh
make setup
make dev
```

See [the development guide](docs/setup/development.md) for database initialization
and user creation. `make test`, `make lint`, `make test-integration` and `make test-ui`
are the same entry points used by CI. The OCR gate needs private samples and a
target host; it cannot pass from synthetic tests.

Read [AGENTS.md](AGENTS.md), the shared contracts and your track's status before
editing. Keep changes within your owned paths and preserve the other track's
append-only registrations. New behavior needs a focused test. Use type hints,
Ruff with a 100-character line length, TypeScript strict mode and server
components by default. Keep public examples synthetic and do not import AGPL code.

Use Conventional Commits and the PR template. Include requirements, milestone,
validation evidence and a status update. Report security issues privately using
[SECURITY.md](SECURITY.md).

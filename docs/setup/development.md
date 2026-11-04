# Development setup

Use Python 3.12, Node 22.12+, Docker Compose, `uv`, `make` and `gitleaks`.
The first dependency install requires network access. Unit tests do not need
provider keys, real documents or network access.

```sh
make setup
docker compose -f deploy/compose.dev.yml up -d --wait
make db-upgrade
uv run docuhive user create admin --admin
make dev
```

Open `http://localhost:3000`. The Python API listens on `127.0.0.1:8000`;
PostgreSQL on `127.0.0.1:5432`; Gotenberg on `127.0.0.1:3001`.
`GET /api/system/health` is a liveness check. It does not claim that the archive
backend or storage is ready. The web scaffold is not a completed archive UI.

Configuration defaults come from [the example environment](../../.env.example).
If you copy it to `.env`, restrict permissions with `chmod 600 .env` and keep it
out of Git. Production requires a secret of at least 32 bytes and refuses
`AUTH_DISABLED`. Staging must be on local storage, separate from the vault.

## Checks

```sh
make test
make lint
make test-integration
make license-check
make gen-api
```

The integration stack uses a separate `docuhive-test` Compose project and
`docuhive_test` database on port 55432. Its data is disposable. Integration
fixtures refuse a database name without the `_test` suffix. Stop it with
`docker compose -f deploy/compose.test.yml down`.

When multiple developers share a checkout, set `UV_PROJECT_ENVIRONMENT=.venv-oa`
for OA commands so dependency synchronization does not replace another track's
environment. Local sandbox users can set `UV_CACHE_DIR` and `npm_config_cache`
to writable temporary directories. Do not commit machine-specific paths.

## Private OCR gate

After creating the private sample corpus, run:

```sh
make spike-ocr DIR=/private/corpus OUT=/private/ocr-report
uv run python evals/ocr/cer.py /private/reference.txt /private/ocr-report/sample-0001/text.txt
```

The spike copies inputs, bounds parsing/OCR time, and writes CSV and Markdown
reports. An existing nonempty output directory is refused. Expected encrypted
quarantine counts toward gate success; other errors must be reviewed. Reports
contain private filenames/text and must stay out of this repository.

See [the gate record](../decisions/0001-ocr-gate.md) and
[OA status](../Developer-OA/STATUS.md) for the current boundary and next work.

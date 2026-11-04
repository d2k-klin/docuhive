# `services/docuhive`

**Overview.** The Python package: the FastAPI app, the job worker, the AI agents, the email connectors and the database migrations. Installed with uv; run with `make dev`.

## What's here

| Path | What it is |
| --- | --- |
| [`migrations/`](migrations/) | Two independent Alembic environments: `core` for the platform tables and `intel` for the AI, email and chat tables |
| [`src/`](src/) | Installable Python source (src layout) |
| [`tests/`](tests/) | Python tests: contract tests, platform tests, AI and email tests, fixtures and test doubles |
| [`Dockerfile`](Dockerfile) | Container image with Tesseract, OCRmyPDF and Ghostscript |
| [`hatch_build.py`](hatch_build.py) | Carry public defaults and the license through both wheel and source distributions |
| [`pyproject.toml`](pyproject.toml) | Package definition, extras and tool settings |

## Extending

Add dependencies to `pyproject.toml` (AI and mail ones in their extras) and run `uv lock`.

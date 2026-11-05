# `.github/workflows`

**Overview.** CI, the OCR image check, the QA system smoke test, the nightly run and releases. Actions are pinned to commit SHAs and jobs default to read-only permissions.

## What's here

| Path | What it is |
| --- | --- |
| [`ci.yml`](ci.yml) | Lint, types, tests, build, licence and secret checks; integration on main or labelled PRs |
| [`ocr-image.yml`](ocr-image.yml) | Builds the worker image and runs real OCR in it (`make ocr-smoke`), on main and on PRs that touch the image, dependencies or ingest code |
| [`nightly.yml`](nightly.yml) | The full QA run: system, browser, performance and audit checks |
| [`system.yml`](system.yml) | QA smoke test against the full stack on every push to main |
| [`release.yml`](release.yml) | When a version bump lands on main, tags `v<version>` on that commit and publishes the release with its CHANGELOG section; a version already released is skipped |

## Extending

Fast, key-free checks go in `ci.yml`; anything slower belongs in the nightly run. Mirror new commands in the `Makefile`.

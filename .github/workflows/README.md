# `.github/workflows`

**Overview.** CI, the QA system smoke test and the nightly run. Actions are pinned to commit SHAs and jobs default to read-only permissions.

## What's here

| Path | What it is |
| --- | --- |
| [`ci.yml`](ci.yml) | Lint, types, tests, build, licence and secret checks; integration on main or labelled PRs |
| [`nightly.yml`](nightly.yml) | The full QA run: system, browser, performance and audit checks |
| [`system.yml`](system.yml) | QA smoke test against the full stack on every push to main |

## Extending

Fast, key-free checks go in `ci.yml`; anything slower belongs in the nightly run. Mirror new commands in the `Makefile`.

# `.github/workflows`

**Overview.** CI runs formatting, typing, tests, builds, license checks and secret scanning. Integration runs on main or an integration-labelled PR.

## What's here

| Path | What it is |
| --- | --- |
| [ci.yml](ci.yml) | Source, configuration or documentation |

## Extending

Keep additions within the documented ownership boundaries. Update focused tests,
the documentation index and the owning track status when behavior changes.
# QA workflows

`system.yml` builds the isolated stack, runs offline QA, real/fake contracts,
API smoke and zero-retry browser smoke on main or manual dispatch. `nightly.yml`
runs at 02:00 UTC and adds the full browser suite and available benchmark/drill
gates. Missing reference-host or release evidence fails visibly; these workflows
do not claim Ollama, ZAP, mutation, upgrades or all 24 journeys are implemented.
Reports are artifacts, never automatic commits. They use no provider secrets.

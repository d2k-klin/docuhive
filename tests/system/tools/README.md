# `tests/system/tools`

**Overview.** QA command implementations, using the existing Python and browser runtimes.

## What's here

| Path | Purpose |
| --- | --- |
| [qa_plugin.py](qa_plugin.py) | Pytest requirement collection, socket policy, run evidence |
| [trace.py](trace.py) | Generate the requirement matrix and enforce the release evidence gate |
| [cert.py](cert.py), [gateway.py](gateway.py) | Ephemeral localhost TLS and fixed ingress without product egress |
| [browser.py](browser.py) | Run Playwright and retain exact-candidate outcomes |
| [seed.py](seed.py) | Seed only QA's separate system and contract databases |
| [audit.py](audit.py), [bundle.py](bundle.py) | Critical coverage and built-browser exposure checks |
| [release.py](release.py) | Signed release/drill evidence preflight |

## Extending

Keep commands in the root Makefile under `qa-*`. Test parsing and gate logic offline.
Artifacts live in ignored `tmp/qa/`, never in private overlays.

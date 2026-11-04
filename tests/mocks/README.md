# `tests/mocks`

**Overview.** Loopback test services with deterministic responses. They never contact providers.

## What's here

| Path | Purpose |
| --- | --- |
| [server.py](server.py) | Fake LLM, capturing proxy, Gmail/Graph fixtures and notification recorder |
| [scripts.json](scripts.json) | Scripted structured answers, keyed by QA model name |

## Extending

Unknown requests fail. The mail mock reuses CL's recorded synthetic fixtures read-only.
Production connectors still need endpoint overrides; see the QA defect register.
Capture logs contain synthetic request bodies and must stay under `tmp/qa`.

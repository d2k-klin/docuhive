# `tests/system/tools`

**Overview.** QA command implementations, using the existing Python and browser runtimes.

## What's here

| Path | Purpose |
| --- | --- |
| [qa_plugin.py](qa_plugin.py) | Pytest requirement collection, socket policy, run evidence |
| [trace.py](trace.py) | Generate the requirement matrix and enforce the release evidence gate |

## Extending

Keep commands in the root Makefile under `qa-*`. Test parsing and gate logic offline.
Artifacts live in ignored `tmp/qa/`, never in private overlays.

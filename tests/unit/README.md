# `tests/unit`

**Overview.** Repository checks that run in the default suite: documentation links, learning examples and licence rules.

## What's here

| Path | What it is |
| --- | --- |
| [`test_docs.py`](test_docs.py) | Relative documentation links must resolve; future paths should use plain code text |
| [`test_examples.py`](test_examples.py) | Every committed standalone learning example runs without network or provider keys |
| [`test_licenses.py`](test_licenses.py) | The CI gate catches SPDX identifiers and full-name AGPL variants |

## Extending

Keep these fast and network-free.

# `services/docuhive/src/docuhive/duplicates`

**Overview.** Near-duplicate detection: the same document arriving twice in different forms, such as an email PDF and a paper scan. See the [learning note](../../../../../docs/learn/13-near-duplicates.md).

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Signals, the duplicate verdict and the `duplicates.scan` job that records open pairs |

## Extending

Pairs are only ever suggested; nothing here deletes or merges documents.

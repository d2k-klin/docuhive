# `services/docuhive/migrations/core/versions`

**Overview.** Platform schema revisions, applied in order.

## What's here

| Path | What it is |
| --- | --- |
| [`0001_core.py`](0001_core.py) | Core baseline: extensions, unaccented FTS configurations and platform tables |
| [`0002_knowledge_bases.py`](0002_knowledge_bases.py) | Saved scopes and the explicit local-consumer token flag |
| [`0003_archive_tools.py`](0003_archive_tools.py) | Custom fields, saved views and near-duplicate pairs |
| [`0004_document_core.py`](0004_document_core.py) | AI provenance per document and a status index |

## Extending

Never edit a merged revision.

# `services/docuhive/tests/contracts`

**Overview.** Contract tests: the same assertions against the real code and the test doubles, plus a check that the contract document matches the code.

## What's here

| Path | What it is |
| --- | --- |
| [`test_contract_drift.py`](test_contract_drift.py) | The documentation's binding models and function signatures must match the real source |
| [`test_documents_parity.py`](test_documents_parity.py) | Identical assertions against the public fake and real document contracts |
| [`test_fake_core.py`](test_fake_core.py) | Reusable contract assertions for the shared test doubles |
| [`test_ingest_parity.py`](test_ingest_parity.py) | File ownership, synchronous rejection and per-owner dedupe for real and fake ingest |
| [`test_models.py`](test_models.py) | The binding schema must retain a stable, JSON-friendly public surface |

## Extending

Add a case here whenever a shared interface changes.

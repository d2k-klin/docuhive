# `services/docuhive/tests`

**Overview.** Python tests: contract tests, platform tests, AI and email tests, fixtures and test doubles. The default suite needs no network and no API keys.

## What's here

| Path | What it is |
| --- | --- |
| [`contracts/`](contracts/) | Contract tests: the same assertions against the real code and the test doubles, plus a check that the contract document matches the code |
| [`core/`](core/) | Tests for the platform modules; Docker-backed ones are marked `integration` |
| [`fakes/`](fakes/) | Test doubles for the shared interfaces, used by unit tests on both sides |
| [`fixtures/`](fixtures/) | Small fixture files shared by tests |
| [`intel/`](intel/) | Tests for the AI, review, email, search, chat and reminder modules, including the privacy audit |
| [`__init__.py`](__init__.py) | DocuHive tests |
| [`conftest.py`](conftest.py) | Shared synthetic fixtures; integration tests opt into an isolated PostgreSQL URL |

## Extending

Mark tests that need Docker with `integration`, and link them to requirements with `@pytest.mark.req`.

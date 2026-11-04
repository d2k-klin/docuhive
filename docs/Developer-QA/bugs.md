# QA defect register

Local issue records, 2026-11-04. No GitHub issues or labels have been created remotely.
Each anchor is a stable reproduction link for strict xfails. Owners retain their files.

## QA-001

S2 · `bug:oa` · open dependency · OA-M3/M4/M5 · ING-01, ING-05, DOC-03, SRCH-01.

`ingest.incoming_dir/submit`, `documents.*` and `search.hybrid` raise `NotImplementedError`;
the upload and document routes do not exist yet. This is unfinished planned work, not a
regression. Reproduce with the real parameters of `test_documents_parity.py` and
`test_ingest_parity.py`, or `tests/system/test_backend.py::test_upload_deduplication`.
Expected: durable ingestion and searchable documents with the promised manual locks.
Release blocker until the real contract checks pass. Fakes do not satisfy this item.

## QA-002

S2 · `bug:oa` · open dependency · OA-M5 · GUIDE-01, GUIDE-02.

`/api/system/setup-status` and the setup wizard are absent. Reproduce with
`test_routes.py::test_setup_checks_have_actionable_states[system]` and E2E-01.
Expected: storage/security checks and a resumable wizard, not a 404.

## QA-003

S2 · `bug:oa` · open dependency · OA-M6 · CAP-01, CAP-02.

The capture/offline queue is not implemented. E2E-04/E2E-05 are test-ahead skeletons,
disabled with explicit blocker links. They need expansion against the final controls,
page order, compression and IndexedDB implementation before counting as acceptance.

## QA-004

S2 · `bug:integration` · open · QAR-INT-03.

`make qa-boundaries` independently rejects four imports of the OA-private
`docuhive.config.settings`: `ai.cli`, `mail.oauth`, `notify`, `notify.jobs`.
The binding contract exposes `config.load_yaml/overlay_path/prompt/plugins`, not
`get_settings`. Owners must agree on an additive contract or remove those private imports.
QA retains the strict failing contract and does not widen the allow-list.

## QA-005

S2 · `bug:integration` · open testability request · QAR-NF-01, QAR-FN-03.

Gmail and Graph have hard-coded provider endpoints; Anthropic and Bedrock ignore
the routing `base_url`. Test clock and SQL write-origin tagging are absent.
Requested changes are those listed in QA-01 §1.1/1.3, test-only where specified.
The isolated compose network blocks egress. Provider mock self-tests do not prove
the mail or privacy paths work across the full product. Dynamic imports/ORM flushes
also need the requested runtime table-write guard; the static check is partial.

## QA-006

S3 · `bug:integration` · open · QAR-TQ-04.

The shared `postgres` fixture skips without a linked issue when the integration URL
is absent. Reproduce: run the existing integration suite without that variable.
QA commands always supply an isolated URL; owners should make explicitly selected
integration checks fail when their environment is missing.

## QA-007

S2 · `bug:cl` · verified (guides now resolve) · GUIDE-05, QAR-NF-09.

The initial real setup-status checks returned help documents that did not exist:
`docs/setup/ai-providers.md`, `docs/setup/mail-accounts.md`, and
`docs/setup/notifications.md`. Reproduce with
`tests/system/test_routes.py::test_setup_checks_have_actionable_states`.
All three responses were 200 but their referenced local files were absent. On the
final run all three guides exist and the checks pass. QA retained the original
assertions and did not write placeholder guides in another track's area.

## QA-008

S2 · `bug:cl` · verified (coverage fixed by QA tests) · QAR-TQ-02.

The first audit found validators at 94% and fact aggregation at 90%. Independent
QA malformed-value and real SQL aggregation tests now bring these to 100% and
98.31%. `make qa-audit` still correctly refuses vault acceptance because that
implementation is absent (QA-001). Mutation testing remains a separate pending gate.

## QA-009

S3 · `bug:oa` · fixed · WEB-04, QAR-NF-05.

The nine implemented static production pages render Times despite the configured
Inter token. Reproduce with `make qa-e2e`; the UI test attaches computed measurements.
On the 1280-light login page: expected family `inter`, actual family `Times`;
controls measured 36 px and heading 20 px / 600, with no horizontal overflow.
The font variable is applied on `body`, while the root font token resolves on
`html`; OA should correct where the variable is available. QA has not edited UI code.

**Fixed:** the font variable now sits on `<html>`, where `--font-sans` is resolved. `make qa-e2e`
passes 72 tests at 375/768/1280 in light and dark (30 skipped for unbuilt features), including
the font check. The same run found `/ask` overflowing at 768 px: the suggestion buttons could not
wrap. They are now wrapping controls (`data-wrap`, control height as a minimum), and the
height check treats `data-wrap` elements as at least control height.

## Triage handling

Use S1–S4, one of `bug:oa`, `bug:cl`, `bug:integration`, and `flaky`/`qa:verified` as needed.
Each remote issue should include the exact local reproduction, candidate revision,
environment, expected/actual result and sanitized evidence. Proposed additions to
the existing bug template: required severity and area dropdowns, requirement IDs,
and a failing-test field. That OA-owned template has not been edited.

S1 blocks the affected area immediately. No release with open S1/S2.
See the [fix policy](05-test-audit-bugs-and-release.md#53-fix-policy).

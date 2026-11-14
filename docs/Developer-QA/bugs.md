# QA defect register

Local issue records, opened 2026-11-04, re-verified 2026-11-14. No GitHub issues or labels have been created remotely.
Each anchor is a stable reproduction link for strict xfails. Owners retain their files.

## QA-001

S2 · `bug:oa` · fixed, verified 2026-11-14 · OA-M3/M4/M5 · ING-01, ING-05, DOC-03, SRCH-01.

Originally `ingest.incoming_dir/submit`, `documents.*` and `search.hybrid` raised
`NotImplementedError` and the upload and document routes did not exist. The real parity
tests and the system upload test run without `xfail` since 2026-11-04. The archive screens
exist: E2E-02 (upload, stored, AI suggestions, review, accept) and E2E-03 (a category chosen
at upload stays locked against the AI) pass at 375/768/1280 in light and dark.

## QA-002

S2 · `bug:oa` · fixed, verified 2026-11-14 · OA-M5 · GUIDE-01, GUIDE-02.

`/api/system/setup-status` exists and `test_setup_checks_have_actionable_states[system]`
runs without `xfail`. Setup shipped as the dashboard checklist, not as a separate wizard:
every check names its state and its next action, and the state comes from the server, so it
survives a reload. E2E-01 was rewritten for the checklist and passes. The step-by-step wizard
in [03-functional-and-e2e.md](03-functional-and-e2e.md) was not built.

## QA-003

S2 · `bug:oa` · fixed, verified 2026-11-14 · OA-M6 · CAP-01, CAP-02.

The capture page and its offline queue exist. E2E-04 (three photos uploaded as one
three-page document) and E2E-05 (captured offline, queued on the device, sent when back
online) pass against the real API, worker and OCR. EXIF rotation and page reordering are
covered by the capture suite in `apps/web/tests/capture`, not by these journeys. Real phones
are still a manual check.

## QA-004

S2 · `bug:integration` · fixed 2026-11-14 · QAR-INT-03.

`ai.cli`, `mail.oauth` and `notify` imported the OA-private `docuhive.config.settings`.
The contract gained two additive functions, `config.default_yaml(name)` and
`config.public_url()`, and the three modules use them. `make qa-boundaries` keeps all three
contracts, and `test_import_linter_contracts` runs without `xfail`.

## QA-005

S2 · `bug:integration` · open testability request · QAR-NF-01, QAR-FN-03.

Gmail and Graph have hard-coded provider endpoints; Anthropic and Bedrock ignore
the routing `base_url`. Test clock and SQL write-origin tagging are absent.
Requested changes are those listed in QA-01 §1.1/1.3, test-only where specified.
The isolated compose network blocks egress. Provider mock self-tests do not prove
the mail or privacy paths work across the full product. Dynamic imports/ORM flushes
also need the requested runtime table-write guard; the static check is partial.

## QA-006

S3 · `bug:integration` · fixed 2026-11-14 · QAR-TQ-04.

The shared `postgres` fixture skipped when the integration URL was absent. Selected by name
(`-m integration`) it now fails instead; an unfiltered local run still skips.

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

## QA-010

S2 · `bug:integration` · fixed 2026-11-14 · QAR-FN-01.

The QA backend image had no Tesseract or Ghostscript, so every upload in the system stack
was quarantined (`MissingDependencyError`) and no journey past login could pass. The image
now uses the production base and OCR packages. The stack's services also restart on failure,
as in production: on a small Docker VM a worker killed for memory came back and finished all
queued jobs, none lost.

## QA-011

S3 · `bug:cl` · fixed 2026-11-14 · WEB-03, WEB-04, QAR-NF-04.

Found by the first full `ui-consistency` run since 0.5.0, fixed in the same change:
the provider choices on `/sources` are two-line cards and are now marked as wrapping
controls; the document link in the AI activity table on `/settings/ai` was distinguishable
by colour only and is now underlined; the loading skeleton had an `aria-label` without a role
and is now a `status`.

## Triage handling

Use S1–S4, one of `bug:oa`, `bug:cl`, `bug:integration`, and `flaky`/`qa:verified` as needed.
Each remote issue should include the exact local reproduction, candidate revision,
environment, expected/actual result and sanitized evidence. Proposed additions to
the existing bug template: required severity and area dropdowns, requirement IDs,
and a failing-test field. That OA-owned template has not been edited.

S1 blocks the affected area immediately. No release with open S1/S2.
See the [fix policy](05-test-audit-bugs-and-release.md#53-fix-policy).

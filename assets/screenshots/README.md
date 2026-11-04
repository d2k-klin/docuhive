# `assets/screenshots`

**Overview.** Real DocuHive screenshots for the
[main README](../../README.md), captured on 2026-11-04 in the isolated QA stack.
All accounts, model responses and usage figures are synthetic.

## What's here

| Path | What it is |
| --- | --- |
| [ask-light.png](ask-light.png) | Initial Ask screen at 1280 × 900, light theme |
| [ask-dark.png](ask-dark.png) | The same Ask screen in dark theme |
| [ai-settings-dark.png](ai-settings-dark.png) | AI provider, routing and privacy settings in dark theme |

The PNGs are unchanged browser captures from the QA production-build sweep.
The user `alice` is the seeded synthetic administrator; the `qa` provider is a
scripted local HTTP service. These images show the interface, not acceptance of
the full document workflow. They preserve the known font issue recorded in the
[verification report](../../docs/Developer-QA/reports/initial-verification.md).

## Extending

1. Start the synthetic stack with `make qa-up`; see the
   [QA harness guide](../../tests/e2e/README.md) for browser configuration.
2. Sign in with the synthetic QA account, use a 1280 × 900 viewport, and capture
   `/ask` in light and dark themes and `/settings/ai` in dark theme.
3. Wait for loading to finish. Capture the real page without replacing content,
   changing styles or adding example answers in the browser.
4. Inspect each image for personal data, credentials and unexpected errors.
   Replace these files, update the capture date and check the root README in
   both themes.

Keep temporary browser traces and logs under ignored `tmp/qa/`. Commit only the
reviewed screenshots. These screenshots are distributed under the repository's
[Apache-2.0 license](../../LICENSE).

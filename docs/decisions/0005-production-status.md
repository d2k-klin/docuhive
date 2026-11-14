# Production status: declared by the owner

Date: 2026-11-14 · State: accepted · Decision: **production-ready (declared by the owner)**

## Context

Until 0.5.0 the README called DocuHive pre-alpha and "not ready for real documents",
and the [production-readiness plan](../shared/production-readiness.md) tied the status
label to the QA release gate, which stands at NO-GO
([v1 acceptance](../Developer-QA/reports/v1-acceptance.md)).

## Decision

On 2026-11-14 the owner declared DocuHive production-ready. The README badge and status
section, the installation guide and the production-readiness plan say so from this date.
The version stays 0.5.0; 1.0.0 is still tied to the release gate.

## Validation and consequences

This is an owner decision, not a gate result, and the evidence is limited. That is
recorded here rather than hidden:

- Verified: the platform, document intake, vault, search, capture, the production
  Compose stack, and backup, restore and vault-rebuild drills, all with synthetic data
  on a development machine
  ([report](../Developer-QA/reports/local-production-validation-2026-11-05.md)); the
  security checklist and an OWASP ZAP baseline with no failures.
- Not recorded in this repository: runs against real AI providers and mailboxes,
  real-document OCR measurements ([OCR gate](0001-ocr-gate.md)), backup, restore and
  storage-outage drills on the target host and NAS, three consecutive nightly backups,
  and checks on real phones.

The QA release gate is unchanged and still NO-GO. Phase 6 of the production-readiness
plan stays open and closes these items; revisit this decision if any of them fails.

# QA execution plan

Scope: QA-owned tests, harnesses, workflows and documents, plus additive shared
test configuration. Developer OA/CL documents and production code stay untouched.

1. **Establish evidence.** Read all QA plans and binding skills, run the existing
   suites, preserve the dirty checkout. Implement requirement collection, a manual
   register, strict acceptance gates and reproducible local defect records.
2. **Build the isolated harness.** Reuse the existing Postgres/Gotenberg compose
   services. Build real API/worker/web images. Seed separate system and contract
   databases. Capture synthetic provider HTTP, block product egress, and use
   localhost HTTPS for real secure-cookie checks. Generate the corpus reproducibly.
3. **Verify what exists.** Contract/model drift, real/fake parity, real PostgreSQL
   and worker recovery, scopes, SQL visibility and currency totals, API/browser
   flows, accessibility/layout, browser exposure, coverage and documentation links.
   Record defects against their owners; retain failing assertions.
4. **Finish dependency-bound acceptance when implementations land.** Replace the
   five real archive xfails after their contracts pass; expand the first five
   journey skeletons and implement E2E-06…24 against the completed product. Add the
   full mail profiles, all-path privacy matrix, reference-host performance, ZAP,
   mutation, visual approvals, upgrade and restore/NAS drills. The current
   `qa-drills` is an evidence preflight, not an implemented drill runner.
5. **Release only with evidence.** Generate the strict matrix, sign real manual
   checks, run every journey twice, resolve S1/S2 and obtain OA/CL acknowledgements.
   The owner tags the release. No synthetic test can satisfy a hardware gate.

Current results and remaining dependencies: [STATUS](STATUS.md),
[verification report](reports/initial-verification.md), [defects](bugs.md).

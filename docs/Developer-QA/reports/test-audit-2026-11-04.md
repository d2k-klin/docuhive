# Test audit — 2026-11-04

Candidate: concurrently developed checkout; no frozen release SHA.

The initial complete default Python run reached 85.01% lines, enforcing sockets
off with Unix sockets allowed for async tests. Critical module measurements were:
validators 94%, fact aggregation 90%, privacy 96%, permission predicates 71%,
metadata mutation 98%. QA is adding independent SQL predicate checks to cover
the administrator/owner/shared/trash combinations. Real vault and dedupe code is
still absent; exercising stubs does not satisfy their critical coverage gate.

The final default suite has 309 passes and 85.34% overall lines. Independent QA
checks bring validators to 100%, fact aggregation to 98.31% and permissions to
100%. Privacy remains 95.83% and metadata mutation 98.25%. The vault implementation
is absent, so the critical gate still correctly rejects complete acceptance.

`make qa-audit` records current coverage and then enforces the 95% critical floor.
Mutation testing and its 80% kill threshold have not run. No mutation success is claimed.

The shared integration fixture can skip without a linked issue ([QA-006](../bugs.md#qa-006)).
Default suites are key-free; explicit integration runs use only QA's disposable database.
No test was retried silently. Browser failures retain screenshots, traces and measured
controls/fonts for triage. Real/fake document and ingest assertions share one implementation
of each assertion; current real parameters are strict, exception-specific expected failures.

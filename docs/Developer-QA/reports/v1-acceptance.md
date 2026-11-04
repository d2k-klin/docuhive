# v1 acceptance

Decision: **NO-GO** · 2026-11-04 · development tree, no release candidate frozen.

The real archive contracts are not implemented, I1–I9 are not all verified, and the
24 journeys have not passed twice on the reference host. Hardware, real OAuth,
privacy across all provider/task paths, performance, recovery, upgrade, security
and mutation evidence are pending. No manual checks have been signed.

Run `make qa-release` on the final candidate. A complete release report also needs
OA and CL acknowledgement. No tag or release is created by QA.
See [status](../STATUS.md), [defects](../bugs.md) and [traceability](../traceability.md).

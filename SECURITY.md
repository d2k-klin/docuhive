# Security

Report vulnerabilities through [a private GitHub advisory](https://github.com/d2k-klin/docuhive/security/advisories/new).
Do not post document contents, credentials or exploit details in public issues.

This repository is under development; no production release is currently supported.
The target deployment is LAN/Tailscale-only. Passwords use Argon2id, sessions and
API tokens are stored hashed, and administrators have no automatic access to
another user's private documents. Production mode refuses disabled authentication
or a missing/short secret. These guarantees require the milestone acceptance
checks in [OA status](docs/Developer-OA/STATUS.md); unfinished archive endpoints
remain unavailable.

"""Check QA's critical coverage floor without changing the developers' tests or thresholds."""

import json
import sys

from qa_plugin import ROOT

CRITICAL = [
    "agents/validators.py",
    "agents/tools/facts.py",
    "ai/privacy.py",
    "auth/permissions.py",
    "documents/metadata.py",
]


def main() -> None:
    report = ROOT / "tmp/qa/coverage.json"
    if not report.exists():
        sys.exit("Run make qa-audit first to create coverage evidence")
    data = json.loads(report.read_text())
    gaps = []
    for module in CRITICAL:
        filename = "services/docuhive/src/docuhive/" + module
        percent = data["files"].get(filename, {}).get("summary", {}).get("percent_covered", 0)
        print(f"{module}: {percent:.2f}% (required 95%)")
        if percent < 95:
            gaps.append(module)
    # Missing production modules cannot earn coverage by exercising their stubs.
    if not (ROOT / "services/docuhive/src/docuhive/vault").is_dir():
        gaps.append("vault implementation absent")
    if gaps:
        sys.exit("Critical coverage gate pending: " + ", ".join(gaps))


if __name__ == "__main__":
    main()

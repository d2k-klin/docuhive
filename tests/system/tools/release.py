"""Fail closed until release/drill evidence exists for the exact candidate tree."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from qa_plugin import ROOT, fingerprint

REQUIRED = {
    "privacy",
    "security",
    "performance",
    "accessibility",
    "visual-approved",
    "resilience",
    "upgrade",
    "mutation",
    "coverage",
    "providers",
    "hygiene",
    "I1",
    "I2",
    "I3",
    "I4",
    "I5",
    "I6",
    "I7",
    "I8",
    "I9",
    "oa-acknowledgement",
    "cl-acknowledgement",
}
REQUIRED |= {f"E2E-{number:02}-run-{run}" for number in range(1, 25) for run in (1, 2)}
DRILLS = {
    "nas-down",
    "worker-killed",
    "db-rebuild",
    "provider-down",
    "budget-exceeded",
    "token-revoked",
    "disk-pressure",
    "converter-down",
    "backup-restore",
}


def missing_evidence(data: dict, required: set[str], candidate: str, root: Path) -> list[str]:
    if data.get("candidate") != candidate:
        return sorted(required)
    missing = []
    for name in sorted(required):
        record = data.get("checks", {}).get(name, {})
        path = (root / record.get("artifact", "")).resolve()
        if (
            record.get("result") != "passed"
            or record.get("runner") in {None, "", "pending"}
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", record.get("date", ""))
            or not path.is_relative_to((root / "tmp/qa").resolve())
            or not path.is_file()
        ):
            missing.append(name)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != record.get("sha256"):
            missing.append(name)
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drills", action="store_true")
    args = parser.parse_args()
    evidence = ROOT / "tmp/qa/release-evidence.json"
    data = json.loads(evidence.read_text()) if evidence.is_file() else {}
    required = DRILLS if args.drills else REQUIRED | DRILLS
    missing = missing_evidence(data, required, fingerprint(), ROOT)
    if not args.drills:
        from trace import manual_entries, signed_manual

        manual = manual_entries((ROOT / "docs/Developer-QA/manual-checks.md").read_text())
        missing += [entry["id"] for entry in manual if not signed_manual(entry)]
        bugs = (ROOT / "docs/Developer-QA/bugs.md").read_text()
        if re.search(r"^S[12] .* · open", bugs, re.M):
            missing.append("open S1/S2 defects")
    if missing:
        sys.exit("NO-GO. Missing current signed evidence: " + ", ".join(missing))
    print("Evidence gate passed. The repo owner still owns release tagging.")


if __name__ == "__main__":
    main()

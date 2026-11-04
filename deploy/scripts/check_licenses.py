"""Fail on AGPL Python distributions; subprocess tools are listed separately."""

import json
import subprocess
import sys


def forbidden_license(license_name: str) -> bool:
    value = license_name.casefold().replace("-", " ")
    return "agpl" in value or "affero" in value


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json"],
        check=True,
        capture_output=True,
        text=True,
    )
    forbidden = [
        row["Name"] for row in json.loads(result.stdout) if forbidden_license(row["License"])
    ]
    if forbidden:
        print("AGPL dependencies are not permitted: " + ", ".join(sorted(forbidden)))
        return 1
    print("Python license gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

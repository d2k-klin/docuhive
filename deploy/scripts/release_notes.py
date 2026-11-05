"""Print the release notes for one version from CHANGELOG.md, for `gh release create`.

Usage: python deploy/scripts/release_notes.py 0.4.1
Relative links become absolute links to that version's tag, so they work on the release page.
"""

import re
import sys
from pathlib import Path

REPO = "https://github.com/d2k-klin/docuhive"


def notes(changelog: str, version: str) -> str:
    sections = re.split(r"^## \[", changelog, flags=re.M)
    current = next((s for s in sections if s.startswith(f"{version}]")), None)
    if current is None:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    later = sections[sections.index(current) + 1 :]
    previous = re.match(r"([0-9][^\]]*)\]", later[0]) if later else None
    body = current.split("\n", 1)[1].strip()
    body = re.sub(r"\]\((?!https?://|#)([^)]+)\)", rf"]({REPO}/blob/v{version}/\1)", body)
    if previous:
        body += f"\n\nFull changes: {REPO}/compare/v{previous[1]}...v{version}"
    return body + "\n"


if __name__ == "__main__":
    print(notes(Path("CHANGELOG.md").read_text(), sys.argv[1]), end="")

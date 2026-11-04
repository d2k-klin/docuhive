"""Relative documentation links must resolve; future paths should use plain code text."""

import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]


def heading_anchors(text: str) -> set[str]:
    result: set[str] = set()
    duplicates: dict[str, int] = {}
    in_code = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        if in_code or not re.match(r"^#{1,6} ", line):
            continue
        title = re.sub(r"^#+\s+", "", line).strip().lower()
        title = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", title)
        slug = "".join(
            char
            for char in title
            if char in " -_" or char.isalnum() or unicodedata.category(char).startswith("M")
        )
        slug = slug.replace(" ", "-")
        count = duplicates.get(slug, 0)
        duplicates[slug] = count + 1
        result.add(f"{slug}-{count}" if count else slug)
    return result


def test_relative_documentation_links():
    documents = list((ROOT / "docs").rglob("*.md")) + list(ROOT.glob("*.md"))
    documents += list((ROOT / ".agents").rglob("*.md"))
    failures = []
    for document in documents:
        content = re.sub(r"```.*?```", "", document.read_text(), flags=re.S)
        for match in re.finditer(r"(?<!!)\[[^]\n]+\]\(([^)]+)\)", content):
            href = match.group(1).split(' "', 1)[0].strip("<>")
            url = urlsplit(href)
            if url.scheme or url.netloc or not href:
                continue
            target = (document.parent / unquote(url.path)).resolve() if url.path else document
            if not target.exists():
                failures.append(f"{document.relative_to(ROOT)} -> {href}")
            elif url.fragment and target.suffix == ".md":
                if unquote(url.fragment) not in heading_anchors(target.read_text()):
                    failures.append(f"{document.relative_to(ROOT)} -> missing anchor {href}")
    assert not failures, "\n".join(failures)

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "release_notes", ROOT / "deploy/scripts/release_notes.py"
)
assert spec and spec.loader
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)

CHANGELOG = """# Changelog

## [Unreleased]

## [0.4.1] - 2026-11-05

### Fixed

- Storage, see the [guide](docs/setup/installation.md) or [anchor](#x) or [site](https://example.org).

## [0.4.0] - 2026-11-05

- Older.
"""


def test_notes_for_one_version_with_absolute_links():
    out = release_notes.notes(CHANGELOG, "0.4.1")
    assert out.startswith("### Fixed") and "Older." not in out
    assert "(https://github.com/d2k-klin/docuhive/blob/v0.4.1/docs/setup/installation.md)" in out
    assert "(#x)" in out and "(https://example.org)" in out
    assert out.endswith("compare/v0.4.0...v0.4.1\n")


def test_every_released_version_in_the_changelog_has_notes():
    text = (ROOT / "CHANGELOG.md").read_text()
    assert release_notes.notes(text, "0.4.0").strip()

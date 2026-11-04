"""Compare two vault snapshots by content; never includes filenames in its report."""

import argparse
import hashlib
from pathlib import Path


def inventory(root: Path) -> dict[str, str]:
    result = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise ValueError("Drill snapshots must not contain symlinks")
        if not path.is_file() or relative.parts[0] in {"library", "consume", "_system"}:
            continue
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        result[str(relative)] = digest.hexdigest()
    return result


def verify(original: Path, restored: Path) -> None:
    expected = inventory(original)
    if not expected or not any(path.endswith("/meta.json") for path in expected):
        raise ValueError("The reference snapshot has no documents")
    if expected != inventory(restored):
        raise ValueError("Restored document bytes or metadata differ")
    print(f"Verified {len(expected)} files; restored bytes and metadata match")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("restored", type=Path)
    args = parser.parse_args()
    verify(args.original, args.restored)


if __name__ == "__main__":
    main()

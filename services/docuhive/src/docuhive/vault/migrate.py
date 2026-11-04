"""`meta.json` schema versions: an ordered list of upgrades, applied when a file is read.

`docuhive vault migrate` rewrites files that are older than the current version.
"""

from collections.abc import Callable

# MIGRATIONS[n - 1] turns a version-n document into version n + 1; append, never edit.
MIGRATIONS: list[Callable[[dict], dict]] = []
CURRENT = len(MIGRATIONS) + 1


def upgrade(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("meta.json must be an object")
    version = data.get("schema")
    if not isinstance(version, int) or isinstance(version, bool) or not 1 <= version <= CURRENT:
        raise ValueError(f"Unsupported meta.json schema: {version!r}")
    for number, step in enumerate(MIGRATIONS[version - 1 :], start=version):
        data = step(data) | {"schema": number + 1}
    return data

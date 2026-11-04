"""Read-only handles on OA's core tables (contracts §5: CL may read, never write).

Using the very Table objects OA's `auth.visible_docs` refers to keeps joins correct.
Tests replace `table` with SQLite stand-ins (tests/fakes/intel.py).
"""

from sqlalchemy import Table


def table(name: str) -> Table:
    import docuhive.db.models  # noqa: F401  registers OA's tables on CoreBase.metadata
    from docuhive.db import CoreBase

    return CoreBase.metadata.tables[name]

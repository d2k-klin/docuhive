"""Taxonomy loader (contract I7): config/defaults/taxonomy.yaml + overlay, validated and cached."""

import re
from functools import lru_cache

from pydantic import ValidationError

from docuhive import config
from docuhive.contracts import Category, Taxonomy

_CATEGORY_ID = re.compile(r"^[a-z0-9-]+(/[a-z0-9-]+)*$")
_SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
_ISO639_1 = re.compile(r"^[a-z]{2}$")


class TaxonomyError(ValueError):
    pass


def validate(raw: dict) -> Taxonomy:
    """Parse and check the rules the Pydantic model cannot express. Errors name their path."""
    try:
        tax = Taxonomy.model_validate(raw)
    except ValidationError as e:
        lines = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
        raise TaxonomyError("; ".join(lines)) from None
    errors: list[str] = []

    def dupes(kind: str, values: list[str]) -> None:
        seen: set[str] = set()
        for v in values:
            if v in seen:
                errors.append(f"duplicate {kind} {v!r}")
            seen.add(v)

    dupes("category", [c.id for c in tax.categories])
    dupes("document type", [t.id for t in tax.document_types])
    dupes("tag", tax.tags)
    ids = {c.id for c in tax.categories}
    for c in tax.categories:
        if not _CATEGORY_ID.match(c.id):
            errors.append(f"category {c.id!r}: ids are lowercase words joined by '/'")
        elif "/" in c.id and c.id.rsplit("/", 1)[0] not in ids:
            errors.append(f"category {c.id!r}: parent {c.id.rsplit('/', 1)[0]!r} is missing")
    for t in tax.document_types:
        dupes(f"fact in {t.id}", [f.name for f in t.facts])
        errors += [f"{t.id}.{f.name}: not snake_case" for f in t.facts if not _SNAKE.match(f.name)]
    if not tax.languages:
        errors.append("languages must not be empty")
    errors += [
        f"language {lang!r} is not ISO 639-1" for lang in tax.languages if not _ISO639_1.match(lang)
    ]
    if errors:
        raise TaxonomyError("; ".join(errors))
    return tax


@lru_cache
def load() -> Taxonomy:
    return validate(config.load_yaml("taxonomy.yaml"))


def reload() -> None:
    load.cache_clear()


def tree(categories: list[Category]) -> list[dict]:
    """Categories nested by '/' for the UI: [{id, label, restricted, children: [...]}]."""
    nodes = {c.id: {**c.model_dump(), "children": []} for c in categories}
    roots: list[dict] = []
    for c in categories:
        parent = c.id.rsplit("/", 1)[0] if "/" in c.id else None
        (nodes[parent]["children"] if parent in nodes else roots).append(nodes[c.id])
    return roots


def document_type(tax: Taxonomy, type_id: str | None):  # type: ignore[no-untyped-def]
    return next((t for t in tax.document_types if t.id == type_id), None)

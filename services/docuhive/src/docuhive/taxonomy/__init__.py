"""Taxonomy loader (contract I7): config/defaults/taxonomy.yaml + overlay, validated and cached."""

import re
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, ValidationError

from docuhive import config
from docuhive.contracts import Category, DocumentType, Taxonomy

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
def defaults() -> Taxonomy:
    return validate(config.load_yaml("taxonomy.yaml"))


# (plugin id, contribution) for every running plugin, in dependency order (filled at start).
CONTRIBUTIONS: list[tuple[str, "Contribution"]] = []


class Contribution(BaseModel):
    """What a plugin adds: new categories, document types and tags, and new facts on existing
    document types. It never changes or removes an entry someone else defined."""

    model_config = ConfigDict(extra="forbid")
    categories: list[Category] = []
    document_types: list[DocumentType] = []
    tags: list[str] = []


def contribute(tax: Taxonomy, plugin_id: str, add: Contribution) -> None:
    source = f"plugin:{plugin_id}"
    categories = {c.id for c in tax.categories}
    for c in add.categories:
        if c.id not in categories:
            tax.categories.append(c.model_copy(update={"source": source}))
            categories.add(c.id)
    types = {t.id: t for t in tax.document_types}
    for t in add.document_types:
        if t.id not in types:
            tax.document_types.append(t.model_copy(update={"source": source}, deep=True))
            continue
        names = {f.name for f in types[t.id].facts}
        types[t.id].facts += [f for f in t.facts if f.name not in names]
    tax.tags += [tag for tag in add.tags if tag not in tax.tags]


def load() -> Taxonomy:
    tax = defaults().model_copy(deep=True)
    categories = config.get_setting("taxonomy.categories")
    if categories is not None:
        tax = validate(tax.model_dump() | {"categories": categories})
    for plugin_id, add in CONTRIBUTIONS:
        contribute(tax, plugin_id, add)
    return validate(tax.model_dump()) if CONTRIBUTIONS else tax


def reload() -> None:
    defaults.cache_clear()


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

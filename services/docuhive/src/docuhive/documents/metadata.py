"""Pure metadata changes used to keep the fake and eventual backend semantics aligned."""

from decimal import Decimal, InvalidOperation

from docuhive.contracts import ApplyResult, DocumentView, MetadataPatch


def apply_view(
    doc: DocumentView, patch: MetadataPatch, *, actor: str, force: bool = False
) -> ApplyResult:
    if actor != "system" and not (actor.startswith("user:") or actor.startswith("ai:")):
        raise ValueError("Unknown metadata actor")
    is_user, is_ai = actor.startswith("user:"), actor.startswith("ai:")
    if patch.unlock_fields and not is_user:
        raise ValueError("Only a user can unlock manual fields")
    changes: dict = {}
    for name in (
        "title",
        "document_date",
        "language",
        "category",
        "document_type",
        "correspondent",
    ):
        value = getattr(patch, name)
        if value is not None:
            if isinstance(value, str):
                value = " ".join(value.split())
            if name == "title" and len(value) > 120:
                raise ValueError("Title must contain at most 120 characters")
            changes[name] = value
    if patch.tags_add or patch.tags_remove:
        added, removed = [tag.strip() for tag in patch.tags_add], set(patch.tags_remove)
        if any(not tag or len(tag) > 64 for tag in added):
            raise ValueError("Tags must contain 1–64 characters")
        changes["tags"] = sorted((set(doc.tags) | set(added)) - removed)
    for key, value in (patch.facts or {}).items():
        if value:
            if value.type in {"money", "number"}:
                try:
                    number = Decimal(value.value)
                except InvalidOperation as error:
                    raise ValueError(f"Invalid numeric fact: {key}") from error
                if not number.is_finite():
                    raise ValueError(f"Invalid numeric fact: {key}")
            elif value.type == "date":
                from datetime import date

                date.fromisoformat(value.value)
        changes[f"facts.{key}"] = value
    applied, skipped = [], []
    manual = set(doc.manual_fields)
    for field, value in changes.items():
        if (
            is_ai
            and not force
            and (field in manual or (field.startswith("facts.") and "facts" in manual))
        ):
            skipped.append(field)
            continue
        if field.startswith("facts."):
            key = field[6:]
            before = doc.facts.get(key)
            if value is None:
                doc.facts.pop(key, None)
            else:
                doc.facts[key] = value
        else:
            before = getattr(doc, field)
            setattr(doc, field, value)
        # A user accepting an existing value still takes ownership of that field.
        if before != value or (is_user and field not in manual):
            applied.append(field)
            if is_user:
                manual.add(field)
    if is_user:
        manual -= set(patch.unlock_fields)
    doc.manual_fields = sorted(manual)
    return ApplyResult(applied=applied, skipped_manual=skipped)

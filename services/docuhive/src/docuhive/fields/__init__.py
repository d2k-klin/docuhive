"""Custom fields: household-defined facts that extraction, review, reminders and Ask treat like
the taxonomy's own. Evals keep using `taxonomy.document_type` so they measure the built-in set.
"""

from sqlalchemy import select

from docuhive import db
from docuhive.ai import coretables
from docuhive.contracts import DocumentType, FactField, Taxonomy


def custom_facts(type_id: str) -> list[FactField]:
    t = coretables.table("custom_fields")
    with db.session() as session:
        rows = session.execute(
            select(
                t.c.name,
                t.c.label,
                t.c.type,
                t.c.description,
                t.c.document_types,
                t.c.remind_days_before,
            ).order_by(t.c.id)
        ).all()
    return [
        FactField(
            name=name,
            type=kind,
            description=f"{label}. {description}".strip(" .") if description else label,
            remind_days_before=list(remind or []),
        )
        for name, label, kind, description, types, remind in rows
        if not types or type_id in types
    ]


def document_type(tax: Taxonomy, type_id: str | None) -> DocumentType | None:
    """The taxonomy's document type with this household's custom fields appended."""
    dt = next((t for t in tax.document_types if t.id == type_id), None)
    if dt is None:
        return None
    builtin = {f.name for f in dt.facts}
    extra = [f for f in custom_facts(dt.id) if f.name not in builtin]
    return dt.model_copy(update={"facts": [*dt.facts, *extra]}) if extra else dt

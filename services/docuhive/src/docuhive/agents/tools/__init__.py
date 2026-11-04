"""Tools for the Ask agent. The user, the session scope and the route come from a closure,
never from model arguments. When the route is not local, restricted documents are masked."""

from datetime import date
from typing import Any, cast

from sqlalchemy import or_, select

from docuhive import auth, db, documents, fields, search, taxonomy
from docuhive.agents.classify import top_correspondents
from docuhive.agents.tools.facts import Agg, GroupBy
from docuhive.agents.tools.facts import query_facts as _query_facts
from docuhive.ai import coretables, privacy, routing
from docuhive.ai.router import Route
from docuhive.contracts import CurrentUser, SearchFilters
from docuhive.index.filters import conditions

WITHHELD = "Content withheld: this document is restricted to local models."


def restricted_doc_ids(user: CurrentUser) -> set[str]:
    tax = taxonomy.load()
    cats = [c.id for c in tax.categories if c.restricted]
    tags = routing.load().privacy.restricted_tags
    rules = conditions(SearchFilters(categories=cats)) + conditions(SearchFilters(tags=tags))
    if not rules:
        return set()
    d = coretables.table("documents")
    with db.session() as s:
        return set(s.scalars(select(d.c.id).where(auth.visible_docs(user), or_(*rules))))


def _date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def build_tools(user: CurrentUser, scope: SearchFilters, route: Route) -> list:
    from strands import tool

    masked = set() if route.local else restricted_doc_ids(user)

    @tool
    def search_documents(
        query: str,
        category: str | None = None,
        document_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 10,
    ) -> dict:
        """Find documents by meaning and keywords.

        Args:
            query: what to look for, in the user's words
            category: optional taxonomy category id, e.g. "utilities/electricity"
            document_type: optional document type id, e.g. "invoice"
            date_from: optional ISO date (document date)
            date_to: optional ISO date (document date)
            limit: max results (1-20)
        """
        f = scope.model_copy(
            update={
                "categories": scope.categories or ([category] if category else []),
                "document_types": scope.document_types
                or ([document_type] if document_type else []),
                "date_from": max(filter(None, [scope.date_from, _date(date_from)]), default=None),
                "date_to": min(filter(None, [scope.date_to, _date(date_to)]), default=None),
            }
        )
        hits = search.hybrid(user, query, f, max(1, min(limit, 20)))
        out = []
        for h in hits:
            v = documents.get(h.document_id)
            hidden = v.id in masked
            out.append(
                {
                    "id": v.id,
                    "title": "[restricted]" if hidden else v.title,
                    "date": v.document_date.isoformat() if v.document_date else None,
                    "type": v.document_type,
                    "correspondent": None if hidden else v.correspondent,
                    "snippet": None if hidden else (h.snippet or "")[:300],
                }
            )
        return {"results": out, "summary": f"{len(out)} documents"}

    @tool
    def read_document(document_id: str, max_chars: int = 6000) -> dict:
        """Read one document's metadata, facts and text.

        Args:
            document_id: the id from search_documents
            max_chars: max characters of text (up to 12000)
        """
        try:
            v = documents.get_for_user(document_id, user)
        except documents.NotFound:
            return {"error": "not found", "summary": "not found"}
        if scope.document_ids and v.id not in scope.document_ids:
            return {"error": "outside the chat scope", "summary": "outside scope"}
        if v.id in masked:
            return {
                "id": v.id,
                "title": "[restricted]",
                "content": WITHHELD,
                "summary": "restricted",
            }
        return {
            "id": v.id,
            "title": v.title,
            "category": v.category,
            "type": v.document_type,
            "correspondent": v.correspondent,
            "date": v.document_date.isoformat() if v.document_date else None,
            "facts": {k: f.model_dump(exclude_none=True) for k, f in v.facts.items()},
            "content": documents.get_content(v.id, max(500, min(max_chars, 12000))),
            "summary": v.title or v.id,
        }

    @tool
    def query_facts(
        field: str,
        agg: str = "sum",
        document_type: str | None = None,
        category: str | None = None,
        correspondent: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        group_by: str | None = None,
    ) -> dict:
        """Compute totals and lists from extracted facts with SQL. Use this for every number.

        Args:
            field: fact name, e.g. "amount_total", "end_date", "premium" (see list_vocabulary)
            agg: one of sum, avg, min, max, count, list
            document_type: optional document type id
            category: optional category id (includes its children)
            correspondent: optional correspondent name
            date_from: optional ISO date (document date)
            date_to: optional ISO date (document date)
            group_by: optional month, year, correspondent or category
        """
        if agg not in ("sum", "avg", "min", "max", "count", "list"):
            return {"error": f"unknown agg {agg}", "summary": "error"}
        if group_by not in (None, "month", "year", "correspondent", "category"):
            return {"error": f"unknown group_by {group_by}", "summary": "error"}
        res = _query_facts(
            user,
            scope,
            field,
            cast(Agg, agg),
            document_type=document_type,
            category=category,
            correspondent=correspondent,
            date_from=_date(date_from),
            date_to=_date(date_to),
            group_by=cast(GroupBy, group_by),
            exclude_ids=masked,
        )
        return res

    @tool
    def list_vocabulary() -> dict:
        """The categories, document types (with their fact fields) and top correspondents."""
        tax = taxonomy.load()
        return {
            "categories": [c.id for c in tax.categories],
            "document_types": {
                t.id: [f.name for f in (fields.document_type(tax, t.id) or t).facts]
                for t in tax.document_types
            },
            "correspondents": top_correspondents(100),
            "summary": "vocabulary",
        }

    tools: list[Any] = [search_documents, read_document, query_facts, list_vocabulary]
    return tools


__all__ = ["WITHHELD", "build_tools", "privacy", "restricted_doc_ids"]

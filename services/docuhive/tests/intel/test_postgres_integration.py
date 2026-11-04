"""Real PostgreSQL proof for the CL paths SQLite cannot cover: pgvector search and averages,
the AI-03 CHECK constraint, partial unique review index, and OA's real visible_docs rule."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from docuhive import db
from docuhive.ai.embeddings import hashed
from docuhive.contracts import CurrentUser, SearchFilters
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration
OWNER = CurrentUser(id=1, username="owner", role="admin")
OTHER = CurrentUser(id=2, username="other", role="member")


@pytest.fixture
def pg(postgres, monkeypatch):
    from docuhive.ai import routing
    from docuhive.db import IntelBase

    from tests.fakes.intel import _import_intel_models, use_routing

    monkeypatch.setenv("DOCUHIVE_ENV", "test")
    _import_intel_models()
    names = ", ".join(f'"{t}"' for t in IntelBase.metadata.tables)
    with db.session() as s:
        s.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        s.execute(
            text(
                "INSERT INTO users (id, username, pw_hash, role) VALUES "
                "(1, 'owner', '!', 'admin'), (2, 'other', '!', 'member')"
            )
        )
    use_routing(monkeypatch)
    routing.load()
    return postgres


def add_doc(doc_id: str, owner: int, shared: bool, content: str, amount: str | None = None):
    with db.session() as s:
        s.execute(
            text(
                "INSERT INTO documents (id, owner_id, shared, status, sha256, mime, title, "
                "category, "
                "document_type, document_date, content) VALUES (:id, :o, :sh, 'stored', :id, "
                "'application/pdf', :t, 'utilities/electricity', 'invoice', '2025-11-01', :c)"
            ),
            {"id": doc_id, "o": owner, "sh": shared, "t": content[:20], "c": content},
        )
        if amount:
            s.execute(
                text(
                    "INSERT INTO doc_facts (document_id, field, type, value_text, value_num,"
                    " currency) VALUES (:id, 'amount_total', 'money', :v, :n, 'EUR')"
                ),
                {"id": doc_id, "v": amount, "n": Decimal(amount)},
            )


def add_chunks(doc_id: str, texts: list[str]):
    from docuhive.index.models import DocChunk

    with db.session() as s:
        s.add_all(
            DocChunk(
                document_id=doc_id,
                chunk_no=i,
                text=t,
                embedding=hashed(t, 1024),
                embed_model="fake",
            )
            for i, t in enumerate(texts)
        )


def test_pgvector_search_permissions_and_similar(pg):
    from docuhive.index.semantic import semantic_search, similar

    add_doc("01A", 1, False, "Stromrechnung Stadtwerke")
    add_doc("01B", 2, False, "Stromrechnung Stadtwerke privat")
    add_doc("01C", 1, True, "Stromrechnung Oktober Stadtwerke")
    add_chunks("01A", ["Stromrechnung Stadtwerke Verbrauch", "Zahlungsinformationen"])
    add_chunks("01B", ["Stromrechnung Stadtwerke Verbrauch privat"])
    add_chunks("01C", ["Stromrechnung Oktober Stadtwerke Verbrauch"])
    hits = semantic_search(OWNER, "Stromrechnung Stadtwerke", SearchFilters(), 5)
    assert [h.document_id for h in hits][:1] == ["01A"] and "01B" not in {
        h.document_id for h in hits
    }
    assert len({h.document_id for h in hits}) == len(hits)
    assert [h.document_id for h in similar(OWNER, "01A")] == ["01C"]


def test_check_constraint_and_partial_unique_index(pg):
    from docuhive.ai.models import AIRun
    from docuhive.review.models import ReviewItem

    with pytest.raises(IntegrityError), db.session() as s:
        s.add(
            AIRun(
                task="x",
                provider="cloud",
                model="m",
                local=False,
                restricted=True,
                prompt_version="p@1",
                status="ok",
            )
        )
    add_doc("01D", 1, True, "x")
    with db.session() as s:
        s.add(ReviewItem(document_id="01D", kind="field", field="title", status="rejected"))
        s.add(ReviewItem(document_id="01D", kind="field", field="title", status="pending"))
    with pytest.raises(IntegrityError), db.session() as s:
        s.add(ReviewItem(document_id="01D", kind="field", field="title", status="pending"))


def test_query_facts_with_real_visible_docs(pg):
    from docuhive.agents.tools.facts import query_facts

    add_doc("01E", 1, False, "a", "84.20")
    add_doc("01F", 1, False, "b", "90.00")
    add_doc("01G", 2, False, "c", "999.00")
    r = query_facts(OWNER, None, "amount_total", "sum", date_from=date(2025, 1, 1))
    assert r["aggregates"] == [{"group": None, "currency": "EUR", "value": "174.20", "count": 2}]
    assert query_facts(OTHER, None, "amount_total", "sum")["aggregates"][0]["value"] == "999.00"


def test_budget_spend_month_on_postgres(pg):
    from docuhive.ai import budgets, runs
    from docuhive.ai.router import Route

    runs.log(
        "chat",
        Route("cloud", "m", False),
        restricted=False,
        prompt_version="p@1",
        status="ok",
        cost_usd=Decimal("0.5"),
    )
    assert budgets.spent("cloud") == 0.5
    assert budgets.spent("cloud", datetime(2020, 1, 15, tzinfo=UTC)) == 0

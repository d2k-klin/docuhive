"""Independent malformed-value and currency aggregation checks on real production logic."""

from decimal import Decimal

import pytest
from docuhive import db
from docuhive.agents import validators
from docuhive.agents.tools.facts import query_facts
from docuhive.contracts import CurrentUser
from sqlalchemy import create_engine, text


@pytest.mark.req("CLS-05")
@pytest.mark.parametrize(
    "function,value",
    [
        (validators.parse_money, "12--3"),
        (validators.parse_number, "letters"),
        (validators.clean_string, " \n\t "),
    ],
)
def test_malformed_extracted_values_fail_instead_of_becoming_facts(function, value):
    with pytest.raises(validators.Invalid):
        function(value)


@pytest.mark.req("CLS-05")
def test_number_fact_has_canonical_decimal_and_currency_validation():
    assert validators.canonical("number", "12,50") == ("12.50", None)
    with pytest.raises(validators.Invalid):
        validators.parse_money("84.20", currency="not-a-currency")
    assert validators.parse_money("1.234,56 EUR") == (Decimal("1234.56"), "EUR")


@pytest.fixture
def fact_database(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in [
            "CREATE TABLE correspondents (id INTEGER PRIMARY KEY, name TEXT)",
            "CREATE TABLE documents (id TEXT PRIMARY KEY, owner_id INTEGER, shared BOOLEAN, "
            "deleted_at DATETIME, status TEXT, title TEXT, document_date DATE, category TEXT, "
            "correspondent_id INTEGER)",
            "CREATE TABLE doc_facts (document_id TEXT, field TEXT, type TEXT, value_text TEXT, "
            "value_num NUMERIC, currency TEXT)",
        ]:
            connection.execute(text(statement))
        for number, value, currency in ((1, "0.10", "EUR"), (2, "0.20", "EUR"), (3, "9.99", "USD")):
            connection.execute(
                text(
                    "INSERT INTO documents VALUES (:id, 1, 0, NULL, 'stored', "
                    "'Synthetic invoice', NULL, 'utilities', NULL)"
                ),
                {"id": str(number)},
            )
            connection.execute(
                text(
                    "INSERT INTO doc_facts VALUES (:id, 'amount', 'money', "
                    ":value, :value, :currency)"
                ),
                {"id": str(number), "value": value, "currency": currency},
            )
        connection.execute(
            text(
                "INSERT INTO documents VALUES ('private', 2, 0, NULL, 'stored', "
                "'Other user', NULL, 'utilities', NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO doc_facts VALUES ('private', 'amount', 'money', '999', 999, 'EUR')")
        )
        connection.execute(
            text("INSERT INTO doc_facts VALUES ('1', 'policy', 'string', 'synthetic', NULL, NULL)")
        )
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    yield engine
    engine.dispose()


@pytest.mark.req("QA-03", "AUTH-03")
@pytest.mark.parametrize(
    "aggregation,expected", [("sum", "0.30"), ("avg", "0.15"), ("min", "0.10"), ("max", "0.20")]
)
def test_real_fact_query_is_decimal_per_currency_and_filters_other_users(
    fact_database, aggregation, expected
):
    user = CurrentUser(id=1, username="qa", role="admin")
    result = query_facts(user, None, "amount", aggregation)
    assert {item["currency"]: item["value"] for item in result["aggregates"]} == {
        "EUR": expected,
        "USD": "9.99",
    }
    assert result["row_count"] == 3
    assert "private" not in {row["document_id"] for row in result["rows"]}


@pytest.mark.req("QA-03")
def test_fact_query_missing_numeric_value_and_date_are_not_invented(fact_database):
    user = CurrentUser(id=1, username="qa", role="member")
    result = query_facts(user, None, "policy", "sum", group_by="year")
    assert result["aggregates"] == [
        {"group": "unknown", "currency": None, "value": None, "count": 1}
    ]

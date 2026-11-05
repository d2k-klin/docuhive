"""Controlled category choices: no provider, database or network."""

from docuhive.agents.classify import ClassifyOut, make_validator
from docuhive.contracts import Category, DocumentType, Taxonomy


def main() -> None:
    tax = Taxonomy(
        version=1,
        languages=["en"],
        categories=[
            Category(id="finance", label="Finance"),
            Category(id="home-business", label="Home business", description="Business receipts"),
            Category(id="travel", label="Travel", enabled=False),
        ],
        document_types=[DocumentType(id="invoice", label="Invoice")],
        tags=[],
    )
    answer = ClassifyOut(
        category="home-business",
        document_type="invoice",
        title="Business invoice",
        correspondent=None,
        tags=[],
        document_date=None,
        language="en",
        confidence={},
    )
    validate = make_validator(tax, [])
    assert validate(answer).category == "home-business"
    try:
        validate(answer.model_copy(update={"category": "travel"}))
    except ValueError:
        print("Disabled category rejected; custom category accepted.")
    else:
        raise AssertionError("Disabled categories must not be accepted")


if __name__ == "__main__":
    main()

"""Score synthetic document pairs with the production near-duplicate rules: no database needed."""

from datetime import date, timedelta

from docuhive.duplicates import is_duplicate, signals

DAY = date(2026, 3, 2)
EMAIL = {"correspondent_id": 1, "document_date": DAY}
CASES = {
    "paper scan of the same invoice": (
        {"correspondent_id": 1, "document_date": DAY + timedelta(days=1)},
        True,
        0.95,
    ),
    "next month's invoice": (
        {"correspondent_id": 1, "document_date": DAY + timedelta(days=31)},
        True,
        0.99,
    ),
    "another sender, same week": (
        {"correspondent_id": 2, "document_date": DAY + timedelta(days=3)},
        False,
        0.40,
    ),
}


def main() -> None:
    money = {("84.20", "EUR")}
    print("Near-duplicate decisions (signals → verdict):")
    verdicts = {}
    for name, (other, same_amount, similarity) in CASES.items():
        reasons = signals(EMAIL, other, money, money if same_amount else set(), similarity)
        verdicts[name] = is_duplicate(reasons, similarity, dates_known=True)
        print(f"  {name}: {', '.join(reasons) or 'no signals'} → {verdicts[name]}")
    assert verdicts == {
        "paper scan of the same invoice": True,
        "next month's invoice": False,  # same template and amount, but a new period
        "another sender, same week": False,
    }


if __name__ == "__main__":
    main()

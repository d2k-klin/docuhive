"""NFR-04 search latency: seed synthetic documents into a disposable `_test` database and time
`search.hybrid` (words only, the part that runs without an AI provider).

    DOCUHIVE_DATABASE_URL=postgresql+psycopg://…/docuhive_test \
      uv run python deploy/scripts/perf_search.py --documents 20000

Synthetic data only; refuses any database whose name does not end in `_test`.
"""

import argparse
import random
import statistics
import time

from sqlalchemy import text
from sqlalchemy.engine import make_url

WORDS = (
    "invoice electricity water gas insurance policy contract notice period payslip tax "
    "statement bank rent lease receipt warranty vehicle health premium amount due total "
    "Rechnung Strom Wasser Versicherung Vertrag Kündigung Gehalt Steuer Miete Beitrag Frist"
).split()
SENDERS = ["Stadtwerke Muster", "Versicherung Beispiel", "Bank Synthetic", "Vermieter Probe"]
CATEGORIES = ["utilities/electricity", "insurance/health", "finance/banking", "housing/rent"]
QUERIES = ["electricity invoice", "Versicherung Beitrag", "notice period", "rent", "Stromrechnung"]


def seed(count: int) -> None:
    from docuhive import db
    from docuhive.auth import create_user

    rng = random.Random(2026)
    with db.session() as session:  # tests insert users with fixed ids; keep the sequence ahead
        session.execute(
            text("SELECT setval('users_id_seq', (SELECT coalesce(max(id), 1) FROM users))")
        )
    owner = create_user(f"perf-{time.time_ns()}", "synthetic perf password 2026")
    with db.session() as session:
        senders = [
            session.execute(
                text(
                    "INSERT INTO correspondents (name, norm_name) VALUES (:n, :k) "
                    "ON CONFLICT (norm_name) DO UPDATE SET name = excluded.name RETURNING id"
                ),
                {"n": name, "k": name.casefold()},
            ).scalar_one()
            for name in SENDERS
        ]
        rows = []
        for index in range(count):
            body = " ".join(rng.choice(WORDS) for _ in range(rng.randint(150, 600)))
            rows.append(
                {
                    "id": f"PERF{index:022d}",
                    "owner": owner,
                    "sha": f"{index:064d}",
                    "title": f"{rng.choice(WORDS)} {rng.choice(WORDS)} {index}",
                    "content": body,
                    "category": rng.choice(CATEGORIES),
                    "sender": rng.choice(senders),
                }
            )
        session.execute(
            text(
                "INSERT INTO documents (id, owner_id, shared, status, sha256, mime, title, "
                "content, category, correspondent_id, manual_fields, fts_config) VALUES "
                "(:id, :owner, true, 'stored', :sha, 'application/pdf', :title, :content, "
                ":category, :sender, '{}', 'dh_simple')"
            ),
            rows,
        )
        session.execute(
            text(
                "UPDATE documents d SET content_tsv = "
                "setweight(to_tsvector(d.fts_config, coalesce(d.title, '')), 'A') || "
                "setweight(to_tsvector(d.fts_config, coalesce((SELECT c.name FROM correspondents c "
                "WHERE c.id = d.correspondent_id), '')), 'B') || "
                "setweight(to_tsvector(d.fts_config, coalesce(d.content, '')), 'C') "
                "WHERE d.id LIKE 'PERF%'"
            )
        )
        session.execute(text("ANALYZE documents"))


def measure(rounds: int) -> dict:
    from docuhive import db, search
    from docuhive.contracts import CurrentUser, SearchFilters

    with db.session() as session:
        owner = session.execute(
            text("SELECT owner_id FROM documents WHERE id LIKE 'PERF%' LIMIT 1")
        ).scalar_one()
    user = CurrentUser(id=owner, username="perf", role="member")
    search.hybrid(user, "warm up", SearchFilters())
    timings = []
    for _ in range(rounds):
        for query in QUERIES:
            started = time.perf_counter()
            search.hybrid(user, query, SearchFilters(), mode="fts")
            timings.append((time.perf_counter() - started) * 1000)
    timings.sort()
    return {
        "queries": len(timings),
        "median_ms": round(statistics.median(timings), 1),
        "p95_ms": round(timings[int(len(timings) * 0.95) - 1], 1),
        "max_ms": round(timings[-1], 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=int, default=20_000)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--keep", action="store_true", help="Keep the seeded documents")
    args = parser.parse_args()
    from docuhive import db
    from docuhive.config.settings import get_settings

    if not (make_url(get_settings().database_url).database or "").endswith("_test"):
        raise SystemExit("Refusing: the database name must end in _test")
    seed(args.documents)
    try:
        result = measure(args.rounds)
    finally:
        if not args.keep:
            with db.session() as session:
                session.execute(text("DELETE FROM documents WHERE id LIKE 'PERF%'"))
    print({"documents": args.documents, **result, "target_ms": 500})


if __name__ == "__main__":
    main()

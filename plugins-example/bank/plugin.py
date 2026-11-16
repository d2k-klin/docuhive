"""Bank statements become payments; payments are matched to the documents they pay."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from docuhive.sdk import ActionError, FactValue, Registry, Result, User, documents
from sqlalchemy import text

from . import formats, matching

STATEMENT_TYPE = "bank-statement"


def setup(registry: Registry) -> None:
    def owner_user(owner_id: int) -> User:
        return User(id=owner_id, username="", role="member")

    def rules() -> dict:
        found = registry.rules("matching.yaml")
        ignore = registry.rules("ignore.yaml").get("ignore", [])
        return {**found, "ignore": ignore}

    # Import --------------------------------------------------------------------------------

    @registry.on("document.stored")
    def import_statement(event) -> None:
        doc = documents.get(event.document_id)
        if not doc.mime.startswith("text/"):
            return  # statements arrive as the bank's data files; PDFs carry no transactions
        try:
            statement = formats.parse(
                documents.original(doc.id), registry.rules("csv-formats.yaml")
            )
        except formats.NotAStatement:
            return
        save(doc.id, doc.owner_id, statement)

    def save(document_id: str, owner_id: int, statement: formats.Statement) -> int:
        iban = (statement.iban or "unknown").replace(" ", "").upper()
        balanced = statement.balanced()
        with registry.db.session() as s:
            account = s.scalar(
                text(
                    "INSERT INTO accounts (owner_id, iban, currency) VALUES (:o, :i, :c) "
                    "ON CONFLICT (owner_id, iban) DO UPDATE SET iban = EXCLUDED.iban RETURNING id"
                ),
                {"o": owner_id, "i": iban, "c": statement.currency},
            )
            s.execute(
                text(
                    "INSERT INTO statements (document_id, account_id, format, period_start, "
                    "period_end, opening, closing, complete, problem) VALUES (:d, :a, :f, :ps, "
                    ":pe, :op, :cl, :ok, :pr) ON CONFLICT (document_id) DO NOTHING"
                ),
                {
                    "d": document_id,
                    "a": account,
                    "f": statement.format,
                    "ps": statement.period_start,
                    "pe": statement.period_end,
                    "op": statement.opening,
                    "cl": statement.closing,
                    "ok": balanced is not False,
                    "pr": None
                    if balanced is not False
                    else "The opening balance plus the payments does not give the closing balance",
                },
            )
            for tx in statement.transactions:
                s.execute(
                    text(
                        "INSERT INTO transactions (account_id, statement_id, booking_date, "
                        "value_date, amount, currency, counterparty, counterparty_iban, purpose, "
                        "end_to_end_id, bank_reference, fingerprint) VALUES (:a, :d, :bd, :vd, "
                        ":am, :cu, :cp, :ci, :pu, :e2e, :br, :fp) "
                        "ON CONFLICT (account_id, fingerprint) DO NOTHING"
                    ),
                    {
                        "a": account,
                        "d": document_id,
                        "bd": tx.booking_date,
                        "vd": tx.value_date,
                        "am": tx.amount,
                        "cu": tx.currency,
                        "cp": tx.counterparty,
                        "ci": tx.counterparty_iban,
                        "pu": tx.purpose,
                        "e2e": tx.end_to_end_id,
                        "br": tx.bank_reference,
                        "fp": tx.fingerprint(),
                    },
                )
        facts: dict = {"account_iban": FactValue(type="iban", value=iban)}
        if statement.period_start:
            facts["period_start"] = FactValue(type="date", value=statement.period_start.isoformat())
        if statement.period_end:
            facts["period_end"] = FactValue(type="date", value=statement.period_end.isoformat())
        if statement.closing is not None:
            facts["closing_balance"] = FactValue(
                type="money", value=str(statement.closing), currency=statement.currency
            )
        period = (
            f"{statement.period_start:%d.%m.%Y}–{statement.period_end:%d.%m.%Y}"
            if (statement.period_start and statement.period_end)
            else ""
        )
        documents.apply_metadata(
            document_id,
            title=f"Bank statement {iban[-4:]} {period}".strip(),
            document_type=STATEMENT_TYPE,
            category="finance/banking",
            document_date=statement.period_end,
            facts=facts,
            tags_add=["private"] if registry.settings.get("private_statements") else [],
        )
        registry.enqueue("match", {"account_id": account}, dedupe_key=str(account))
        return account

    # Matching --------------------------------------------------------------------------------

    @registry.job("match")
    def match(payload, ctx) -> None:
        settings = rules()
        with registry.db.session() as s:
            owner_id = s.scalar(
                text("SELECT owner_id FROM accounts WHERE id = :a"), {"a": payload["account_id"]}
            )
            open_rows = s.execute(
                text(
                    "SELECT id, booking_date, amount, counterparty, counterparty_iban, "
                    "coalesce(purpose, '') FROM transactions t WHERE account_id = :a "
                    "AND ignored_reason IS NULL AND NOT EXISTS (SELECT 1 FROM matches m "
                    "WHERE m.transaction_id = t.id AND m.state = 'confirmed') ORDER BY booking_date"
                ),
                {"a": payload["account_id"]},
            ).all()
            own_rules = s.execute(
                text("SELECT counterparty, reason FROM match_rules WHERE owner_id = :o"),
                {"o": owner_id},
            ).all()
        if owner_id is None or not open_rows:
            return
        user = owner_user(owner_id)
        ignore = [(r["counterparty"], r["reason"]) for r in settings["ignore"]] + list(own_rules)
        payments = [matching.Payment(*row) for row in open_rows]
        start = min(p.booking_date for p in payments) - timedelta(
            days=settings["window_days_after"]
        )
        end = max(p.booking_date for p in payments) + timedelta(days=settings["window_days_before"])
        pools = {
            "out": [
                c
                for d in documents.find(
                    user,
                    document_type=settings["expense_types"],
                    date_from=start,
                    date_to=end,
                    limit=1000,
                )
                if (c := matching.candidate(d, settings["reference_facts"]))
            ],
            "in": [
                c
                for d in documents.find(
                    user,
                    document_type=settings["income_types"],
                    date_from=start,
                    date_to=end,
                    limit=1000,
                )
                if (c := matching.candidate(d, settings["reference_facts"]))
            ],
        }
        taken: set[str] = set()
        for payment in payments:
            reason = next(
                (
                    why
                    for who, why in ignore
                    if who and matching.normalise(who) in matching.normalise(payment.counterparty)
                ),
                None,
            )
            if reason:
                with registry.db.session() as s:
                    s.execute(
                        text("UPDATE transactions SET ignored_reason = :r WHERE id = :i"),
                        {"r": reason, "i": payment.id},
                    )
                continue
            pool = [
                c
                for c in pools["in" if payment.amount > 0 else "out"]
                if c.document_id not in taken
            ]
            how, document_id, suggestions = matching.decide(payment, pool, settings)
            with registry.db.session() as s:
                s.execute(
                    text("DELETE FROM matches WHERE transaction_id = :t AND state = 'suggested'"),
                    {"t": payment.id},
                )
                if document_id:
                    confirm(s, payment.id, document_id, abs(payment.amount), how, "rule")
                    taken.add(document_id)
                for doc_id, score in suggestions:
                    s.execute(
                        text(
                            "INSERT INTO matches (transaction_id, document_id, amount, how, "
                            "state, score) "
                            "VALUES (:t, :d, :a, 'suggested', 'suggested', :s) ON CONFLICT DO "
                            "NOTHING"
                        ),
                        {"t": payment.id, "d": doc_id, "a": abs(payment.amount), "s": score},
                    )
            if document_id:
                paid(document_id, payment.booking_date, payment.id, abs(payment.amount))

    def confirm(
        s, transaction_id: int, document_id: str, amount: Decimal, how: str, by: str
    ) -> None:
        s.execute(
            text(
                "INSERT INTO matches (transaction_id, document_id, amount, how, state, "
                "confirmed_by, "
                "confirmed_at) VALUES (:t, :d, :a, :h, 'confirmed', :b, :at) ON CONFLICT "
                "(transaction_id, document_id) DO UPDATE SET state = 'confirmed', how = :h, "
                "confirmed_by = :b, confirmed_at = :at"
            ),
            {
                "t": transaction_id,
                "d": document_id,
                "a": amount,
                "h": how,
                "b": by,
                "at": datetime.now(UTC),
            },
        )
        s.execute(
            text("DELETE FROM matches WHERE transaction_id = :t AND state = 'suggested'"),
            {"t": transaction_id},
        )

    def paid(document_id: str, on: date, transaction_id: int, amount: Decimal) -> None:
        documents.apply_metadata(
            document_id, facts={"paid_on": FactValue(type="date", value=on.isoformat())}
        )
        registry.emit(
            "matched",
            {
                "transaction_id": transaction_id,
                "document_id": document_id,
                "amount": str(amount),
                "date": on.isoformat(),
            },
            key=f"{transaction_id}:{document_id}",
        )

    # For people (screens call these) and for other plugins -----------------------------------

    def visible_accounts(s, user: User) -> list[int]:
        return list(
            s.scalars(text("SELECT id FROM accounts WHERE owner_id = :u OR shared"), {"u": user.id})
        )

    @registry.service
    def accept_suggestion(user: User, transaction_id: int, document_id: str) -> str:
        with registry.db.session() as s:
            row = s.execute(
                text(
                    "SELECT t.booking_date, t.amount FROM transactions t JOIN accounts a ON a.id "
                    "= t.account_id "
                    "WHERE t.id = :t AND a.owner_id = :u"
                ),
                {"t": transaction_id, "u": user.id},
            ).first()
            if row is None:
                raise LookupError("This payment is not in one of your accounts")
            documents.get_for_user(document_id, user)  # the person must see the document too
            confirm(s, transaction_id, document_id, abs(row.amount), "person", f"user:{user.id}")
        paid(document_id, row.booking_date, transaction_id, abs(row.amount))
        return "Matched."

    @registry.service
    def ignore_counterparty(user: User, transaction_id: int, reason: str) -> str:
        with registry.db.session() as s:
            name = s.scalar(
                text(
                    "SELECT t.counterparty FROM transactions t JOIN accounts a ON a.id = "
                    "t.account_id "
                    "WHERE t.id = :t AND a.owner_id = :u"
                ),
                {"t": transaction_id, "u": user.id},
            )
            if not name:
                raise LookupError("This payment is not in one of your accounts")
            s.execute(
                text(
                    "INSERT INTO match_rules (owner_id, counterparty, reason) VALUES (:u, :c, :r)"
                ),
                {"u": user.id, "c": name, "r": reason},
            )
            s.execute(
                text(
                    "UPDATE transactions t SET ignored_reason = :r FROM accounts a WHERE a.id = "
                    "t.account_id "
                    "AND a.owner_id = :u AND t.counterparty = :c AND NOT EXISTS (SELECT 1 FROM "
                    "matches m "
                    "WHERE m.transaction_id = t.id AND m.state = 'confirmed')"
                ),
                {"r": reason, "u": user.id, "c": name},
            )
        return f"Payments to {name} no longer need a document."

    @registry.service
    def payments_for(document_id: str) -> list[dict]:
        """Confirmed payments of one document: [{date, amount, transaction_id}]."""
        with registry.db.session() as s:
            rows = s.execute(
                text(
                    "SELECT t.booking_date, m.amount, t.id FROM matches m JOIN transactions t "
                    "ON t.id = m.transaction_id WHERE m.document_id = :d AND m.state = 'confirmed' "
                    "ORDER BY t.booking_date"
                ),
                {"d": document_id},
            ).all()
        return [{"date": r[0], "amount": r[1], "transaction_id": r[2]} for r in rows]

    @registry.service
    def transactions(
        user: User, *, year: int | None = None, counterparty: str | None = None
    ) -> list[dict]:
        with registry.db.session() as s:
            accounts = visible_accounts(s, user)
            if not accounts:
                return []
            rows = (
                s.execute(
                    text(
                        "SELECT id, account_id, booking_date, amount, currency, counterparty, "
                        "purpose, "
                        "statement_id, ignored_reason FROM transactions WHERE account_id = ANY(:a) "
                        "AND (CAST(:y AS integer) IS NULL OR extract(year FROM booking_date) = :y) "
                        "ORDER BY booking_date DESC, id DESC"
                    ),
                    {"a": accounts, "y": year},
                )
                .mappings()
                .all()
            )
        rows = [dict(r) for r in rows]
        if counterparty:
            rows = [r for r in rows if matching.similar(counterparty, r["counterparty"]) >= 0.8]
        return rows

    # Screens ---------------------------------------------------------------------------------

    def account_rows(user: User) -> list[dict]:
        with registry.db.session() as s:
            return [
                dict(r)
                for r in s.execute(
                    text(
                        "SELECT a.id, coalesce(a.name, a.iban) AS name, a.iban, a.shared, "
                        "a.owner_id, max(st.period_end) AS last_statement, "
                        "(SELECT count(*) FROM transactions t WHERE t.account_id = a.id) "
                        "AS payments "
                        "FROM accounts a LEFT JOIN statements st ON st.account_id = a.id "
                        "WHERE a.owner_id = :u OR a.shared GROUP BY a.id ORDER BY a.id"
                    ),
                    {"u": user.id},
                ).mappings()
            ]

    @registry.data("accounts")
    def accounts(user: User, params: dict) -> list[dict]:
        return account_rows(user)

    @registry.data("account_options")
    def account_options(user: User, params: dict) -> list[dict]:
        return [{"value": str(a["id"]), "label": a["name"]} for a in account_rows(user)]

    @registry.data("transactions")
    def transaction_rows(user: User, params: dict) -> list[dict]:
        with registry.db.session() as s:
            matched = set(
                s.scalars(text("SELECT transaction_id FROM matches WHERE state = 'confirmed'"))
            )
        rows = transactions(user)
        titles: dict[str, str] = {}
        for r in rows:
            sid = r["statement_id"]
            if sid and sid not in titles:
                try:
                    titles[sid] = documents.get_for_user(sid, user).title or "Statement"
                except documents.NotFound:
                    titles[sid] = ""
            r["statement"] = titles.get(sid or "", "")
            r["account"] = str(r["account_id"])
            r["state"] = (
                "Matched"
                if r["id"] in matched
                else "No document needed"
                if r["ignored_reason"]
                else "Open"
            )
        return rows

    @registry.data("suggestions")
    def suggestions(user: User, params: dict) -> list[dict]:
        with registry.db.session() as s:
            rows = s.execute(
                text(
                    "SELECT t.id AS transaction_id, t.booking_date, t.counterparty, t.amount, "
                    "t.currency, m.document_id, m.score FROM transactions t "
                    "JOIN accounts a ON a.id = t.account_id "
                    "LEFT JOIN matches m ON m.transaction_id = t.id AND m.state = 'suggested' "
                    "WHERE a.owner_id = :u AND t.ignored_reason IS NULL AND NOT EXISTS "
                    "(SELECT 1 FROM matches c WHERE c.transaction_id = t.id "
                    "AND c.state = 'confirmed') ORDER BY t.booking_date DESC, m.score DESC"
                ),
                {"u": user.id},
            ).mappings()
            rows = [dict(r) for r in rows]
        for r in rows:
            try:
                r["document_title"] = (
                    documents.get_for_user(r["document_id"], user).title
                    if r["document_id"]
                    else None
                )
            except documents.NotFound:
                r["document_id"] = r["document_title"] = None
        return rows

    def unpaid_documents(user: User) -> list[dict]:
        settings = rules()
        since = date.today() - timedelta(days=365)
        out = []
        for doc in documents.find(user, document_type=settings["expense_types"], date_from=since):
            total = doc.facts.get("amount_total")
            if total and "paid_on" not in doc.facts:
                out.append(
                    {
                        "id": doc.id,
                        "title": doc.title or "Untitled",
                        "document_date": doc.document_date,
                        "correspondent": doc.correspondent,
                        "amount": {"value": total.value, "currency": total.currency or "EUR"},
                    }
                )
        return out

    @registry.data("unpaid")
    def unpaid(user: User, params: dict) -> list[dict]:
        return unpaid_documents(user)

    @registry.data("overview")
    def overview(user: User, params: dict) -> list[dict]:
        open_payments = {r["transaction_id"] for r in suggestions(user, {})}
        last = max(
            (a["last_statement"] for a in account_rows(user) if a["last_statement"]), default=None
        )
        return [
            {"label": "Payments to check", "value": len(open_payments), "format": "number"},
            {
                "label": "Documents without a payment",
                "value": len(unpaid_documents(user)),
                "format": "number",
            },
            {"label": "Latest statement", "value": last, "format": "date"},
        ]

    @registry.data("document_payments")
    def document_payments(user: User, params: dict) -> list[dict]:
        doc = documents.get_for_user(params["document_id"], user)
        with registry.db.session() as s:
            condition = (
                "t.statement_id = :d"
                if doc.document_type == STATEMENT_TYPE
                else "t.id IN (SELECT transaction_id FROM matches WHERE document_id = :d "
                "AND state = 'confirmed')"
            )
            return [
                dict(r)
                for r in s.execute(
                    text(
                        "SELECT t.booking_date, t.counterparty, t.amount, t.currency, "
                        "coalesce(a.name, a.iban) AS account FROM transactions t "
                        f"JOIN accounts a ON a.id = t.account_id WHERE {condition} "
                        "AND (a.owner_id = :u OR a.shared) ORDER BY t.booking_date"
                    ),
                    {"d": doc.id, "u": user.id},
                ).mappings()
            ]

    @registry.action("accept")
    def accept(user: User, params: dict) -> str:
        if not params.get("document_id"):
            raise ActionError("No document is suggested for this payment yet.")
        try:
            return accept_suggestion(user, int(params["transaction_id"]), params["document_id"])
        except (LookupError, documents.NotFound) as error:
            raise ActionError(str(error) or "This payment or document is not yours.") from None

    @registry.action("no_document")
    def no_document(user: User, params: dict) -> str:
        try:
            return ignore_counterparty(user, int(params["transaction_id"]), "No document needed")
        except LookupError as error:
            raise ActionError(str(error)) from None

    @registry.action("rename_account")
    def rename_account(user: User, params: dict) -> Result:
        name = str(params.get("name") or "").strip()
        if not name:
            return Result(errors={"name": "Give the account a name"})
        with registry.db.session() as s:
            changed = s.execute(
                text("UPDATE accounts SET name = :n, shared = :s WHERE id = :a AND owner_id = :u"),
                {
                    "n": name[:80],
                    "s": bool(params.get("shared")),
                    "a": int(params.get("account") or 0),
                    "u": user.id,
                },
            ).rowcount
        if not changed:
            return Result(errors={"account": "Choose one of your own accounts"})
        return Result(message="Saved.")

    # Ask ---------------------------------------------------------------------------------------

    @registry.tool
    def payments(
        user: User,
        counterparty: str | None = None,
        year: int | None = None,
        exclude_ids: set | None = None,
    ) -> dict:
        """What was paid to or received from someone, per currency, from your bank statements.

        Args:
            counterparty: a name such as "Stadtwerke"; leave empty for all payments
            year: a calendar year such as 2026; leave empty for all years
        """
        rows = [
            r
            for r in transactions(user, year=year, counterparty=counterparty)
            if r["statement_id"] not in (exclude_ids or set())
        ]
        totals: dict[str, dict[str, Decimal]] = {}
        for r in rows:
            side = "received" if r["amount"] > 0 else "paid"
            bucket = totals.setdefault(r["currency"], {"paid": Decimal(0), "received": Decimal(0)})
            bucket[side] += abs(r["amount"])
        return {
            "payments": len(rows),
            "totals": {cur: {k: str(v) for k, v in t.items()} for cur, t in totals.items()},
            "documents": sorted({r["statement_id"] for r in rows if r["statement_id"]}),
            "summary": f"{len(rows)} payments"
            + "".join(
                f", {cur} paid {t['paid']}, received {t['received']}" for cur, t in totals.items()
            ),
        }

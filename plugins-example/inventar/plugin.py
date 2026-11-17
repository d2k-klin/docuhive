"""Inventory and warranties: the AI proposes, a person confirms, a list comes out.

1. A receipt with durable goods becomes proposals (checked: the prices cannot add up to more
   than the receipt).
2. A person adds a proposal with its location, or says "not an item" once for good.
3. Warranty manuals and type plates are matched to items; warranties remind before they end.
4. Lists for the insurer and claim bundles are documents in the archive.
"""

import csv
import io
import re
from datetime import date, timedelta
from decimal import Decimal

from docuhive.sdk import ActionError, Registry, Result, User, ai, documents, reminders, render
from pydantic import BaseModel, Field
from sqlalchemy import text

ITEM_FIELDS = (
    "name",
    "category",
    "manufacturer",
    "model",
    "serial_number",
    "location_id",
    "assigned_to",
    "purchase_date",
    "price",
    "notes",
    "shared",
)


class Item(BaseModel):
    name: str
    category: str = "other"
    manufacturer: str | None = None
    model: str | None = None
    quantity: int = Field(default=1, ge=1, le=100)
    unit_price: Decimal = Field(ge=0)
    is_durable: bool
    warranty_months: int | None = Field(default=None, ge=0, le=240)


class Items(BaseModel):
    items: list[Item] = Field(default_factory=list, max_length=20)


class Plate(BaseModel):
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None


def norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    for d in (day.day, 30, 29, 28):
        try:
            return date(year, month + 1, d)
        except ValueError:
            continue
    raise ValueError(day)


def setup(registry: Registry) -> None:  # noqa: C901 - one plugin, many small parts
    def q(sql: str, **params) -> list[dict]:  # type: ignore[no-untyped-def]
        with registry.db.session() as s:
            return [dict(r) for r in s.execute(text(sql), params).mappings()]

    def run(sql: str, **params) -> None:  # type: ignore[no-untyped-def]
        with registry.db.session() as s:
            s.execute(text(sql), params)

    categories = lambda: {c["id"]: c for c in registry.rules("categories.yaml")["categories"]}  # noqa: E731
    limits = lambda: registry.rules("thresholds.yaml")  # noqa: E731

    # A place inside another reads "House › Kitchen". Depth is capped so a loop in the
    # data can never make the query run away (set_parent refuses loops anyway).
    PLACES = (
        "WITH RECURSIVE places AS (SELECT id, name::text AS path, 1 AS depth FROM locations "
        "WHERE parent_id IS NULL UNION ALL SELECT l.id, p.path || ' › ' || l.name, p.depth + 1 "
        "FROM locations l JOIN places p ON l.parent_id = p.id WHERE p.depth < 8) "
    )

    def visible(user: User, item_id: object = None) -> list[dict]:
        sql = (
            PLACES + "SELECT i.*, p.path AS location FROM items i LEFT JOIN places p ON "
            "p.id = i.location_id WHERE (i.owner_id = :u OR i.shared)"
        )
        if item_id is not None:
            sql += " AND i.id = :i"
        return q(sql + " ORDER BY i.name", u=user.id, i=int(item_id or 0))

    def own(user: User, item_id: object) -> dict:
        found = [i for i in visible(user, item_id) if i["owner_id"] == user.id]
        if not found:
            raise ActionError("This item is not yours to change.")
        return found[0]

    def flag(price: Decimal | None) -> str | None:
        if price is None:
            return None
        net = price / Decimal("1.19")  # ponytail: German standard rate; the flag is only a hint
        return "low_value" if net <= Decimal(str(limits()["low_value_up_to"])) else "asset"

    def remind(item: dict) -> None:
        key = f"warranty:{item['id']}"
        if item["state"] == "active" and item["warranty_until"]:
            reminders.set(
                item["owner_id"],
                key,
                f"Warranty ends: {item['name']}",
                item["warranty_until"],
                days_before=[30],
                link=f"/plugins/inventar/item?id={item['id']}",
            )
        else:
            reminders.clear(item["owner_id"], key)

    # 1. Proposals from receipts --------------------------------------------------------------

    def propose(doc) -> None:  # type: ignore[no-untyped-def]
        total = doc.facts.get("amount_total")
        floor = Decimal(str(limits()["propose_from"]))
        if total is None or Decimal(total.value) < floor:
            return
        if doc.category and not any(
            doc.category == c or doc.category.startswith(f"{c}/")
            for c in limits()["document_categories"]
        ):
            return
        if q("SELECT 1 FROM items WHERE created_from_document_id = :d", d=doc.id):
            return
        known = categories()

        def check(answer: Items) -> Items:
            spent = sum((i.unit_price * i.quantity for i in answer.items), Decimal(0))
            if spent > Decimal(total.value) * Decimal("1.01") + 1:
                raise ValueError("The items cost more than the receipt's total")
            for i in answer.items:
                if i.category not in known:
                    i.category = "other"
            return answer

        try:
            answer = ai.ask(
                "item",
                Items,
                document=doc,
                validate=check,
                variables={"categories": ", ".join(known)},
            )
        except ai.Unavailable:
            return
        dismissed = {
            r["name"]
            for r in q(
                "SELECT name FROM dismissed WHERE owner_id = :o AND seller = :s",
                o=doc.owner_id,
                s=norm(doc.correspondent),
            )
        }
        bought = doc.document_date or doc.added_at.date()
        for item in answer.items:
            if not item.is_durable or item.unit_price < floor or norm(item.name) in dismissed:
                continue
            months = item.warranty_months or known[item.category]["warranty_months"]
            with registry.db.session() as s:
                item_id = s.execute(
                    text(
                        "INSERT INTO items (owner_id, shared, name, category, manufacturer, model, "
                        "purchase_date, price, quantity, seller, warranty_until, warranty_source, "
                        "business_flag, created_from_document_id) "
                        "VALUES (:o, :sh, :n, :c, :m, :mo, :d, "
                        ":p, :qty, :s, :w, :ws, :f, :doc) RETURNING id"
                    ),
                    {
                        "o": doc.owner_id,
                        "sh": doc.shared,
                        "n": item.name[:200],
                        "c": item.category,
                        "m": item.manufacturer,
                        "mo": item.model,
                        "d": bought,
                        "p": item.unit_price,
                        "qty": item.quantity,
                        "s": doc.correspondent,
                        "w": add_months(bought, months),
                        "ws": "document" if item.warranty_months else "assumed",
                        "f": flag(item.unit_price),
                        "doc": doc.id,
                    },
                ).scalar_one()
                s.execute(
                    text(
                        "INSERT INTO item_documents (item_id, document_id, role) VALUES "
                        "(:i, :d, 'receipt')"
                    ),
                    {"i": item_id, "d": doc.id},
                )

    def match(doc, role: str) -> None:  # type: ignore[no-untyped-def]
        """A warranty card or manual for an item the owner has: suggested, a person confirms."""
        facts = {k: norm(v.value) for k, v in doc.facts.items()}
        words = norm(f"{doc.title} {documents.content(doc.id, 4000)}")
        for item in q(
            "SELECT * FROM items WHERE owner_id = :o AND state = 'active'", o=doc.owner_id
        ):
            keys = [norm(item["serial_number"]), norm(item["model"])]
            if any(k and (k in facts.values() or k in words) for k in keys):
                run(
                    "INSERT INTO item_documents (item_id, document_id, role, suggested) VALUES "
                    "(:i, :d, :r, true) ON CONFLICT DO NOTHING",
                    i=item["id"],
                    d=doc.id,
                    r=role,
                )

    @registry.on("document.classified")
    def classified(event) -> None:  # type: ignore[no-untyped-def]
        doc = documents.get(event.document_id)
        if event.document_type in ("receipt", "invoice"):
            propose(doc)
        elif event.document_type in ("warranty", "manual"):
            match(doc, event.document_type)

    # 2. A person decides -----------------------------------------------------------------------

    def location_id(user: User, name: str | None) -> int | None:
        if not name or not str(name).strip():
            return None
        if str(name).isdigit():
            return int(name)
        with registry.db.session() as s:
            return s.execute(
                text(
                    "INSERT INTO locations (owner_id, name) VALUES (:o, :n) "
                    "ON CONFLICT (owner_id, name) "
                    "DO UPDATE SET name = EXCLUDED.name RETURNING id"
                ),
                {"o": user.id, "n": str(name).strip()},
            ).scalar_one()

    @registry.action("add_item")
    def add_item(user: User, params: dict) -> Result:
        item = own(user, params.get("id"))
        name = str(params.get("name") or item["name"]).strip()
        run(
            "UPDATE items SET state = 'active', name = :n, location_id = coalesce(:l, location_id) "
            "WHERE id = :i",
            n=name,
            l=location_id(user, params.get("location")),
            i=item["id"],
        )
        remind(own(user, item["id"]))
        return Result(message=f"“{name}” is in your inventory.")

    @registry.action("not_an_item")
    def not_an_item(user: User, params: dict) -> str:
        item = own(user, params.get("id"))
        run(
            "INSERT INTO dismissed (owner_id, seller, name) VALUES (:o, :s, :n) "
            "ON CONFLICT DO NOTHING",
            o=user.id,
            s=norm(item["seller"]),
            n=norm(item["name"]),
        )
        run("DELETE FROM items WHERE id = :i", i=item["id"])
        return "Removed. The same thing from this shop will not be proposed again."

    @registry.action("save_item")
    def save_item(user: User, params: dict) -> Result:
        """Create an item by hand, or correct one. A warranty date entered here is the person's."""
        values = {}
        for field in ITEM_FIELDS:
            if field not in params:
                continue
            value = params[field]
            if field == "location_id":
                value = location_id(user, value)
            elif field == "purchase_date":
                value = date.fromisoformat(value) if value else None
            elif field == "price":
                value = Decimal(str(value)) if value not in (None, "") else None
            elif field == "shared":
                value = bool(value)
            else:
                value = value or None
            values[field] = value
        warranty = params.get("warranty_until")
        if warranty:
            values |= {"warranty_until": date.fromisoformat(warranty), "warranty_source": "person"}
        if "price" in values:
            values["business_flag"] = flag(values["price"])
        if params.get("id"):
            item = own(user, params["id"])
            if values:
                run(
                    "UPDATE items SET "
                    + ", ".join(f"{k} = :{k}" for k in values)
                    + " WHERE id = :id",
                    **values,
                    id=item["id"],
                )
            remind(own(user, item["id"]))
            return Result(message="Saved.")
        if not values.get("name"):
            return Result(errors={"name": "What is it?"})
        values.setdefault("category", "other")
        if "warranty_until" not in values and values.get("purchase_date"):
            months = categories()[values["category"]]["warranty_months"]
            values |= {
                "warranty_until": add_months(values["purchase_date"], months),
                "warranty_source": "assumed",
            }
        columns = {"owner_id": user.id, "state": "active", **values}
        with registry.db.session() as s:
            item_id = s.execute(
                text(
                    f"INSERT INTO items ({', '.join(columns)}) "
                    f"VALUES ({', '.join(':' + c for c in columns)}) "
                    "RETURNING id"
                ),
                columns,
            ).scalar_one()
        remind(own(user, item_id))
        return Result(message="Added.", goto=f"item?id={item_id}")

    @registry.action("confirm_document")
    def confirm_document(user: User, params: dict) -> str:
        own(user, params.get("item"))
        run(
            "UPDATE item_documents SET suggested = false WHERE item_id = :i AND document_id = :d",
            i=int(params["item"]),
            d=params["document"],
        )
        return "Linked."

    @registry.action("attach_document")
    def attach_document(user: User, params: dict) -> str:
        item = own(user, params.get("id"))
        doc = documents.get_for_user(params["document"], user)
        role = params.get("role") or "other"
        run(
            "INSERT INTO item_documents (item_id, document_id, role) VALUES (:i, :d, :r) "
            "ON CONFLICT (item_id, document_id) DO UPDATE SET role = :r, suggested = false",
            i=item["id"],
            d=doc.id,
            r=role,
        )
        if role == "type_plate":
            try:
                plate = ai.ask("type-plate", Plate, document=doc)
            except ai.Unavailable:
                return "Linked. The type plate could not be read; enter the serial number by hand."
            run(
                "UPDATE items SET serial_number = coalesce(serial_number, :s), "
                "model = coalesce(model, "
                ":m), manufacturer = coalesce(manufacturer, :f) WHERE id = :i",
                s=plate.serial_number,
                m=plate.model,
                f=plate.manufacturer,
                i=item["id"],
            )
            return f"Linked. Read from the plate: {plate.serial_number or 'no serial number'}."
        return "Linked."

    @registry.action("leave")
    def leave(user: User, params: dict) -> str:
        item = own(user, params.get("id"))
        state = params.get("state") or "disposed"
        if state not in ("sold", "disposed", "lost"):
            raise ActionError("Choose sold, disposed or lost.")
        run(
            "UPDATE items SET state = :s, disposed_on = :d WHERE id = :i",
            s=state,
            d=date.today(),
            i=item["id"],
        )
        remind(own(user, item["id"]))
        return "The item stays in the history but leaves your lists."

    FILLED = (
        "category",
        "manufacturer",
        "model",
        "serial_number",
        "location_id",
        "assigned_to",
        "purchase_date",
        "price",
        "seller",
        "warranty_until",
        "warranty_source",
        "notes",
        "business_flag",
        "created_from_document_id",
    )

    @registry.action("merge", destructive=True)
    def merge(user: User, params: dict) -> Result:
        """The same thing twice (two receipts, or a proposal and a hand-made entry): keep this
        one, fill its empty fields from the other, take over its documents, drop the other."""
        keep, other = own(user, params.get("id")), own(user, params.get("other"))
        if keep["id"] == other["id"]:
            raise ActionError("Choose another item.")
        fill = ", ".join(f"{c} = coalesce(k.{c}, o.{c})" for c in FILLED)
        with registry.db.session() as s:
            s.execute(
                text(f"UPDATE items k SET {fill} FROM items o WHERE k.id = :k AND o.id = :o"),
                {"k": keep["id"], "o": other["id"]},
            )
            s.execute(
                text(
                    "INSERT INTO item_documents (item_id, document_id, role, suggested) "
                    "SELECT :k, document_id, role, suggested FROM item_documents WHERE item_id "
                    "= :o ON CONFLICT (item_id, document_id) DO NOTHING"
                ),
                {"k": keep["id"], "o": other["id"]},
            )
            s.execute(text("DELETE FROM items WHERE id = :o"), {"o": other["id"]})
        reminders.clear(user.id, f"warranty:{other['id']}")
        remind(own(user, keep["id"]))
        return Result(message=f"Merged “{other['name']}” into this item.")

    @registry.data("merge_options")
    def merge_options(user: User, params: dict) -> list[dict]:
        here = str(params.get("id") or "")
        return [
            {"value": str(i["id"]), "label": f"{i['name']} ({i['purchase_date'] or 'no date'})"}
            for i in visible(user)
            if i["owner_id"] == user.id
            and str(i["id"]) != here
            and i["state"] in ("active", "proposed")
        ]

    # 4. Lists and bundles ----------------------------------------------------------------------

    def active(user: User, minimum: Decimal = Decimal(0)) -> list[dict]:
        return [i for i in visible(user) if i["state"] == "active" and (i["price"] or 0) >= minimum]

    @registry.action("contents_list")
    def contents_list(user: User, params: dict) -> Result:
        minimum = Decimal(str(params.get("minimum") or 0))
        items = active(user, minimum)
        if not items:
            raise ActionError("There are no items to list.")
        groups: dict[str, list[dict]] = {}
        for i in items:
            groups.setdefault(i["location"] or "Without a location", []).append(i)
        totals = {
            k: sum((i["price"] or Decimal(0)) * i["quantity"] for i in v) for k, v in groups.items()
        }
        pdf = render.pdf(
            "contents-list.html",
            {
                "groups": groups,
                "totals": totals,
                "total": sum(totals.values(), Decimal(0)),
                "on": date.today().strftime("%d.%m.%Y"),
                "minimum": minimum,
                "categories": categories(),
            },
        )
        doc_id = documents.create(
            user,
            pdf,
            filename=f"contents-list-{date.today()}.pdf",
            title=f"Contents list {date.today():%d.%m.%Y}",
            category="insurance/home",
            document_date=date.today(),
        )
        return Result(message="The list is ready.", goto=f"/documents/{doc_id}")

    @registry.action("claim_bundle")
    def claim_bundle(user: User, params: dict) -> Result:
        """One PDF: a cover sheet, then each document of the item in order."""
        import pikepdf

        item = own(user, params.get("id"))
        rows = q(
            "SELECT document_id, role FROM item_documents WHERE item_id = :i AND NOT suggested "
            "ORDER BY array_position(ARRAY['receipt','warranty','type_plate','photo','repair',"
            "'manual','other'], role)",
            i=item["id"],
        )
        cover = render.pdf(
            "claim-bundle.html",
            {
                "item": item,
                "documents": [documents.get(r["document_id"]).title or r["role"] for r in rows],
                "on": date.today().strftime("%d.%m.%Y"),
            },
        )
        bundle = pikepdf.Pdf.open(io.BytesIO(cover))
        included = []
        for r in rows:
            try:
                data = documents.archive_pdf(r["document_id"])
            except documents.NotFound:
                continue
            with pikepdf.Pdf.open(io.BytesIO(data)) as part:
                bundle.pages.extend(part.pages)
            included.append(r["document_id"])
        out = io.BytesIO()
        bundle.save(out)
        bundle.close()
        doc_id = documents.create(
            user,
            out.getvalue(),
            filename=f"claim-{norm(item['name'])}.pdf",
            title=f"Claim bundle: {item['name']}",
            derived_from=included,
            document_date=date.today(),
        )
        return Result(message="The bundle is ready.", goto=f"/documents/{doc_id}")

    @registry.action("export_csv")
    def export_csv(user: User, params: dict) -> Result:
        out = io.StringIO()
        writer = csv.writer(out, delimiter=";")
        writer.writerow(
            [
                "name",
                "category",
                "location",
                "manufacturer",
                "model",
                "serial_number",
                "purchase_date",
                "price",
                "currency",
                "warranty_until",
                "business_flag",
            ]
        )
        for i in active(user):
            writer.writerow(
                [
                    i["name"],
                    i["category"],
                    i["location"] or "",
                    i["manufacturer"] or "",
                    i["model"] or "",
                    i["serial_number"] or "",
                    i["purchase_date"] or "",
                    i["price"] or "",
                    i["currency"],
                    i["warranty_until"] or "",
                    i["business_flag"] or "",
                ]
            )
        return Result(download=("inventory.csv", out.getvalue().encode("utf-8-sig"), "text/csv"))

    # Screens -----------------------------------------------------------------------------------

    def row(i: dict) -> dict:
        days = (i["warranty_until"] - date.today()).days if i["warranty_until"] else None
        return i | {
            "value": {
                "value": (i["price"] or Decimal(0)) * i["quantity"],
                "currency": i["currency"],
            }
            if i["price"] is not None
            else None,
            "warranty": None
            if days is None
            else "Ended"
            if days < 0
            else "Ends soon"
            if days <= 60
            else "Assumed"
            if i["warranty_source"] == "assumed"
            else "Active",
            "category_label": categories().get(i["category"], {}).get("label", i["category"]),
        }

    registry.data("proposals")(
        lambda user, params: [
            row(i) for i in visible(user) if i["state"] == "proposed" and i["owner_id"] == user.id
        ]
    )
    registry.data("items")(lambda user, params: [row(i) for i in active(user)])
    registry.data("warranties")(
        lambda user, params: sorted(
            (
                row(i)
                for i in active(user)
                if i["warranty_until"]
                and date.today() <= i["warranty_until"] <= date.today() + timedelta(days=366)
            ),
            key=lambda r: r["warranty_until"],
        )
    )
    registry.data("proposal_options")(
        lambda user, params: [
            {"value": str(i["id"]), "label": f"{i['name']} ({i['seller'] or 'unknown shop'})"}
            for i in visible(user)
            if i["state"] == "proposed" and i["owner_id"] == user.id
        ]
    )
    registry.data("recent_documents")(
        lambda user, params: [
            {
                "value": d.id,
                "label": f"{d.title or 'Untitled'} ({d.document_date or d.added_at.date()})",
            }
            for d in documents.find(user, limit=200)
        ]
    )
    registry.data("category_options")(
        lambda user, params: [{"value": k, "label": v["label"]} for k, v in categories().items()]
    )

    def places(user: User) -> list[dict]:
        return q(
            PLACES + "SELECT p.id, p.path FROM places p JOIN locations l ON l.id = p.id "
            "WHERE l.owner_id = :o ORDER BY p.path",
            o=user.id,
        )

    registry.data("location_options")(
        lambda user, params: [{"value": str(r["id"]), "label": r["path"]} for r in places(user)]
    )
    registry.data("parent_options")(
        lambda user, params: (
            [{"value": "", "label": "Nowhere else (a place of its own)"}]
            + [{"value": str(r["id"]), "label": r["path"]} for r in places(user)]
        )
    )

    @registry.action("set_parent")
    def set_parent(user: User, params: dict) -> Result:
        """Put a place inside another, such as the kitchen inside the house."""
        mine = {str(r["id"]): r["path"] for r in places(user)}
        place, parent = str(params.get("place") or ""), str(params.get("parent") or "")
        if place not in mine or (parent and parent not in mine):
            raise ActionError("Choose two of your places.")
        if parent and (parent == place or mine[parent].startswith(mine[place] + " › ")):
            return Result(errors={"parent": "A place cannot be inside itself"})
        run(
            "UPDATE locations SET parent_id = :p WHERE id = :i AND owner_id = :o",
            p=int(parent) if parent else None,
            i=int(place),
            o=user.id,
        )
        return Result(message="Saved.")

    registry.data("roles")(
        lambda user, params: [
            {"value": r, "label": r.replace("_", " ").capitalize()}
            for r in ("receipt", "warranty", "manual", "repair", "photo", "type_plate", "other")
        ]
    )
    registry.data("states")(
        lambda user, params: [
            {"value": "sold", "label": "Sold"},
            {"value": "disposed", "label": "Disposed of"},
            {"value": "lost", "label": "Lost or stolen"},
        ]
    )

    @registry.data("item")
    def item_detail(user: User, params: dict) -> dict:
        found = visible(user, params.get("id"))
        if not found:
            raise ActionError("This item does not exist or is not yours.")
        i = row(found[0])
        return i | {"location_id": str(i["location_id"]) if i["location_id"] else None}

    @registry.data("item_documents")
    def item_documents(user: User, params: dict) -> list[dict]:
        item_detail(user, params)
        out = []
        for r in q("SELECT * FROM item_documents WHERE item_id = :i", i=int(params["id"])):
            try:
                doc = documents.get_for_user(r["document_id"], user)
            except documents.NotFound:
                continue
            out.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "role": r["role"],
                    "item": params["id"],
                    "document": doc.id,
                    "status": "Suggested" if r["suggested"] else None,
                }
            )
        return out

    @registry.data("overview")
    def overview(user: User, params: dict) -> list[dict]:
        waiting = sum(
            1 for i in visible(user) if i["state"] == "proposed" and i["owner_id"] == user.id
        )
        soon = registry.data_sources["warranties"](user, params)[:1]
        total = sum(((i["price"] or Decimal(0)) * i["quantity"] for i in active(user)), Decimal(0))
        return [
            {"label": "Proposed items", "value": waiting, "format": "number"},
            {
                "label": "Value of your things",
                "value": {"value": total, "currency": "EUR"},
                "format": "money",
            },
        ] + [
            {"label": f"Warranty ends: {r['name']}", "value": r["warranty_until"], "format": "date"}
            for r in soon
        ]

    @registry.data("document_items")
    def document_items(user: User, params: dict) -> list[dict]:
        documents.get_for_user(params["document_id"], user)
        ids = {
            r["item_id"]
            for r in q(
                "SELECT item_id FROM item_documents WHERE document_id = :d", d=params["document_id"]
            )
        }
        return [row(i) for i in visible(user) if i["id"] in ids]

    @registry.service
    def equipment(user: User, year: int) -> list[dict]:
        """For the tax plugin: business-flagged items bought in a year, with their receipts."""
        out = []
        for i in active(user):
            if i["business_flag"] and i["purchase_date"] and i["purchase_date"].year == year:
                docs = q(
                    "SELECT document_id FROM item_documents WHERE item_id = :i AND role = "
                    "'receipt'",
                    i=i["id"],
                )
                out.append(
                    {
                        "name": i["name"],
                        "bought": i["purchase_date"],
                        "price": i["price"],
                        "currency": i["currency"],
                        "flag": i["business_flag"],
                        "documents": [d["document_id"] for d in docs],
                    }
                )
        return out

    # Ask ---------------------------------------------------------------------------------------

    def in_place(item: dict, place: str) -> bool:
        """ "Kitchen" finds "House › Kitchen"; "House" finds everything in the house."""
        return not place or norm(place) in [norm(p) for p in (item["location"] or "").split("›")]

    @registry.tool
    def inventory_items(user: User, query: str = "", location: str = "") -> dict:
        """Things you own, with price, purchase date and whether the warranty still runs.

        Args:
            query: part of the name, manufacturer or model, such as "washing machine"
            location: a room or place, such as "Kitchen"
        """
        words = norm(query)
        found = [
            row(i)
            for i in active(user)
            if (not words or words in norm(f"{i['name']}{i['manufacturer']}{i['model']}"))
            and in_place(i, location)
        ]
        docs = (
            q(
                "SELECT document_id FROM item_documents WHERE item_id = ANY(:i) AND NOT suggested",
                i=[i["id"] for i in found],
            )
            if found
            else []
        )
        return {
            "items": [
                {
                    "name": i["name"],
                    "location": i["location"],
                    "price": str(i["price"]),
                    "bought": i["purchase_date"] and i["purchase_date"].isoformat(),
                    "warranty_until": i["warranty_until"] and i["warranty_until"].isoformat(),
                    "warranty_assumed": i["warranty_source"] == "assumed",
                }
                for i in found
            ],
            "documents": [d["document_id"] for d in docs],
            "summary": f"{len(found)} items",
        }

    @registry.tool(aggregates_only=True)
    def inventory_value(user: User, location: str = "") -> dict:
        """What your things cost in total, per currency.

        Args:
            location: only this room or place
        """
        totals: dict[str, Decimal] = {}
        for i in active(user):
            if not in_place(i, location):
                continue
            totals[i["currency"]] = (
                totals.get(i["currency"], Decimal(0)) + (i["price"] or 0) * i["quantity"]
            )
        return {
            "totals": {k: str(v) for k, v in totals.items()},
            "documents": [],
            "summary": ", ".join(f"{v} {k}" for k, v in totals.items()) or "nothing yet",
        }

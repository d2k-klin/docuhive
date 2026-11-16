"""Seed only the compose QA database; no resets, no writes to any existing archive."""

from docuhive.auth import create_user
from docuhive.config.settings import get_settings
from docuhive.db import session
from docuhive.db.migrations import migrate
from docuhive.db.models import User
from sqlalchemy import select
from sqlalchemy.engine import make_url

PASSWORD = "synthetic qa password 2026"


def main() -> None:
    settings = get_settings()
    url = make_url(settings.database_url)
    if settings.env != "test" or url.database != "docuhive_test" or url.host != "postgres":
        raise ValueError("QA seed is restricted to the isolated compose database")
    import psycopg

    with psycopg.connect(
        host="postgres",
        user="docuhive_test",
        password="docuhive_test",
        dbname="postgres",
        autocommit=True,
    ) as connection:
        if not connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", ("docuhive_contract_test",)
        ).fetchone():
            connection.execute("CREATE DATABASE docuhive_contract_test")
    migrate("upgrade")
    from docuhive import vault

    vault.init()  # the isolated e2e volume; refuses any folder that is not empty and not a vault
    for name, admin in (("alice", True), ("bob", False)):
        with session() as db:
            exists = db.scalar(select(User.id).where(User.username == name))
        if exists is None:
            create_user(name, PASSWORD, admin=admin)
    seed_plugins()


def seed_plugins() -> None:
    """Switch on the example plugins and give alice a little made-up data in each, once."""
    from docuhive.contracts import CurrentUser
    from docuhive.plugins import discovery, runtime, state
    from docuhive.profiles import ProfileIn, list_for, save

    for found in discovery.discover():
        if found.loadable and found.manifest is not None and found.id not in state.states():
            state.enable(found.id, found.manifest.capability_names(), actor="qa-seed")
    runtime.start("worker")
    with session() as db:
        alice_id = db.scalar(select(User.id).where(User.username == "alice"))
    alice = CurrentUser(id=alice_id, username="alice", role="admin")
    if list_for(alice):
        return  # seeded before

    def act(plugin: str, action: str, /, **params: object) -> object:
        return runtime.LOADED[plugin].registry.actions[action][0](alice, params)

    def data(plugin: str, source: str, /, **params: object) -> list:
        return runtime.LOADED[plugin].registry.data_sources[source](alice, params)

    me = save(
        alice,
        ProfileIn(
            kind="business",
            name="Muster Design",
            tax_number="12/345/67890",
            email="post@example.org",
            phone="+49 30 1234567",
            address={"street": "Beispielweg 1", "postcode": "12345", "city": "Musterstadt"},
            bank={"holder": "Muster Design", "iban": "DE89 3704 0044 0532 0130 00"},
        ),
    )
    if "steuer-de" in runtime.LOADED:
        act(
            "steuer-de",
            "save_book",
            name="Studio",
            kind="euer",
            chart="skr03",
            vat_period="quarterly",
            profile_id=str(me.id),
        )
        act(
            "steuer-de",
            "save_customer",
            name="Kunde Beispiel GmbH",
            street="Hauptstraße 5",
            postcode="54321",
            city="Beispielstadt",
            email="buchhaltung@example.org",
        )
        customer = data("steuer-de", "customers")[0]["id"]
        act(
            "steuer-de",
            "save_draft",
            customer_id=str(customer),
            service_to="2026-03-31",
            lines=[
                {
                    "description": "Beratung",
                    "quantity": "8",
                    "unit": "HUR",
                    "unit_price": "95.00",
                    "vat_code": "sale_19",
                }
            ],
        )
        act(
            "steuer-de",
            "add_entry",
            direction="income",
            entry_date="2026-03-10",
            counterparty="Kunde Eins",
            gross="1190.00",
            vat_code="sale_19",
            account="8400",
            paid_on="2026-03-12",
        )
    if "inventar" in runtime.LOADED:
        act(
            "inventar",
            "save_item",
            name="Waschmaschine",
            category="appliance",
            purchase_date="2026-03-02",
            price="649.00",
            location_id="Küche",
        )
    if "vermieter-de" in runtime.LOADED:
        act(
            "vermieter-de",
            "save_property",
            name="Hauptstraße 5",
            street="Hauptstraße 5",
            postcode="54321",
            city="Beispielstadt",
            profile_id=str(me.id),
        )
        prop = str(data("vermieter-de", "properties")[0]["id"])
        act("vermieter-de", "save_unit", property=prop, name="EG", area="40")
        unit = str(data("vermieter-de", "units")[0]["id"])
        act(
            "vermieter-de",
            "save_tenancy",
            unit=unit,
            tenant_name="Mieter Eins",
            start_date="2025-01-01",
            rent="500",
            advance="100",
            persons="1",
        )


if __name__ == "__main__":
    main()

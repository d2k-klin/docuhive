"""The rule data in rules/: years, VAT treatments and charts of accounts, read through custom/."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from docuhive.sdk import ActionError


class RulesMissing(ActionError):
    """There is no rules file for a year: such a year cannot be closed. Shown on the page as is."""


@dataclass
class Rules:
    registry: Any

    def year(self, year: int) -> dict:
        try:
            data = self.registry.rules(f"years/{year}.yaml")
        except FileNotFoundError:
            raise RulesMissing(
                f"There are no rules for {year} yet. A plugin update brings them; until then "
                f"{year} cannot be closed."
            ) from None
        if data.get("draft"):
            raise RulesMissing(f"The rules for {year} are a draft and cannot be used yet.")
        return data

    def version(self, year: int) -> str:
        data = self.year(year)
        return f"{year}{'' if data.get('reviewed') else '-unreviewed'}"

    def vat_codes(self) -> dict[str, dict]:
        return {c["id"]: c for c in self.registry.rules("vat-codes.yaml")["codes"]}

    def chart(self, chart: str) -> dict:
        data = self.registry.rules(f"accounts-{chart}.yaml")
        data["by_id"] = {str(a["id"]): a for a in data["accounts"]}
        return data

    def account(self, chart: str | None, account_id: str | None) -> dict | None:
        if not chart or not account_id:
            return None
        return self.chart(chart)["by_id"].get(str(account_id))

    def deductible(self, chart: str | None, account_id: str | None) -> Decimal:
        account = self.account(chart, account_id) or {}
        return Decimal(str(account.get("deductible", 1)))

    def rate(self, code: str) -> Decimal:
        return Decimal(str(self.vat_codes()[code]["rate"]))

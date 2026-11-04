"""Monthly USD caps per provider, computed from ai_runs (calendar month, UTC)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from docuhive import db
from docuhive.ai import routing
from docuhive.ai.models import AIRun
from docuhive.ai.router import Route


class BudgetExceeded(Exception):
    def __init__(self, provider: str, spent: float, cap: float):
        super().__init__(f"{provider}: spent ${spent:.2f} of ${cap:.2f} this month")
        self.provider, self.spent, self.cap = provider, spent, cap


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(now: datetime | None = None) -> datetime:
    start = month_start(now)
    return (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )


def spent(provider: str, now: datetime | None = None) -> float:
    start = month_start(now)
    end = next_month_start(now)
    with db.session() as s:
        total = s.scalar(
            select(func.coalesce(func.sum(AIRun.cost_usd), 0)).where(
                AIRun.provider == provider, AIRun.at >= start, AIRun.at < end
            )
        )
    return float(total or 0)


def cost(route: Route, tokens_in: int | None, tokens_out: int | None) -> Decimal | None:
    if route.local:
        return Decimal(0)
    price = routing.load().pricing.get(str(route))
    if price is None:
        return None
    usd = (tokens_in or 0) * price.in_ / 1e6 + (tokens_out or 0) * price.out / 1e6
    return Decimal(str(round(usd, 5)))


def check(route: Route) -> None:
    cap = routing.load().budgets.get(route.provider)
    if cap is None or route.local:
        return
    used = spent(route.provider)
    if used >= 0.8 * cap:
        _warn(route.provider, used, cap)
    if used >= cap:
        raise BudgetExceeded(route.provider, used, cap)


def _warn(provider: str, used: float, cap: float) -> None:
    from docuhive.notify import Notification, send_once

    month = month_start().strftime("%Y-%m")
    pct = 100 if used >= cap else 80
    send_once(
        f"budget:{provider}:{month}:{pct}",
        Notification(
            kind="budget",
            title=f"AI budget {pct}% used: {provider}",
            body=f"{provider} has used ${used:.2f} of its ${cap:.2f} monthly budget.",
            url="/settings/ai",
            user_id=None,
        ),
        window=timedelta(days=31),
    )

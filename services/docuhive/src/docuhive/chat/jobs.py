"""analyses.run {analysis_id, user}: run a saved analysis to completion and store the result."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from docuhive import db, jobs
from docuhive.ai.budgets import BudgetExceeded, next_month_start
from docuhive.chat import collect
from docuhive.chat.models import Analysis
from docuhive.contracts import CurrentUser, SearchFilters


@jobs.handler("analyses.run", queue="ai", timeout_s=900)
def run(payload: dict, ctx: Any) -> None:
    user = CurrentUser(**payload["user"])
    with db.session() as s:
        a = s.get(Analysis, payload["analysis_id"])
        if a is None or a.user_id != user.id:
            return
        prompt, scope, route = a.prompt, SearchFilters(**a.filters), a.route
    try:
        result = asyncio.run(collect(user, prompt, scope=scope, route=route))
    except BudgetExceeded as e:
        ctx.defer(next_month_start(), f"budget: {e}")
    except Exception as e:  # noqa: BLE001 - shown on the analysis page instead of a silent failure
        result = {
            "error": f"{type(e).__name__}: {e}",
            "markdown": "",
            "citations": [],
            "facts_rows": [],
            "ai_run_id": None,
        }
    with db.session() as s:
        a = s.get(Analysis, payload["analysis_id"])
        if a is not None:
            a.last_result, a.last_run_at = result, datetime.now(UTC)

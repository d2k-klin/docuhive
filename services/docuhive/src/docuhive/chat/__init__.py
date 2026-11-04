"""Chat sessions and saved analyses around the Ask agent."""

from collections.abc import AsyncIterator
from typing import Any

from docuhive.agents.ask import ask
from docuhive.contracts import CurrentUser, SearchFilters


async def collect(
    user: CurrentUser,
    prompt: str,
    *,
    scope: SearchFilters,
    route: str | None,
    task: str = "analyse",
) -> dict:
    """Run the Ask agent to completion (saved analyses): markdown, citations, facts rows."""
    facts_rows: list[dict] = []
    done: dict[str, Any] = {}
    events: AsyncIterator[dict] = ask(user, [], prompt, scope=scope, route=route, task=task)
    async for ev in events:
        if (
            ev["type"] == "tool_result"
            and ev["name"] == "query_facts"
            and isinstance(ev.get("result"), dict)
        ):
            facts_rows += ev["result"].get("rows", [])
        elif ev["type"] == "done":
            done = ev
    return {
        "markdown": done.get("text", ""),
        "citations": done.get("citations", []),
        "facts_rows": facts_rows,
        "ai_run_id": done.get("ai_run_id"),
        "uncited": done.get("uncited", False),
    }

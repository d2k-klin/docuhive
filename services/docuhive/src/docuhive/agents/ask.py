"""Ask agent: a tool-using chat over the archive with citations (QA-01..03)."""

import re
from collections.abc import AsyncIterator
from datetime import date

from docuhive import documents
from docuhive.agents.base import run_agent
from docuhive.agents.tools import build_tools
from docuhive.ai import routing
from docuhive.contracts import CurrentUser, SearchFilters

CITATION = re.compile(r"\[doc:([0-9A-Za-z]{10,40})\]")
HISTORY = 20  # ponytail: older turns are dropped, not summarised; add a summary if chats get long


def citations(text: str, user: CurrentUser) -> list[dict]:
    """[doc:<id>] ids in order, minus ids the user cannot see (defence in depth)."""
    out: list[dict] = []
    for doc_id in dict.fromkeys(CITATION.findall(text)):
        try:
            v = documents.get_for_user(doc_id, user)
        except documents.NotFound:
            continue
        out.append({"document_id": v.id, "title": v.title})
    return out


def is_uncited(text: str, cited: list[dict]) -> bool:
    # ponytail: "factual content" = the answer states a number; refine with an eval if noisy.
    return not cited and bool(re.search(r"\d", CITATION.sub("", text)))


async def ask(
    user: CurrentUser,
    history: list[dict],
    question: str,
    *,
    scope: SearchFilters | None = None,
    local_only: bool = False,
    route: str | None = None,
    task: str = "chat",
) -> AsyncIterator[dict]:
    """Stream harness events, then one `citation` event per cited document, then `done` with
    citations and the uncited flag. `history` holds earlier {role, content} messages."""
    scope = scope or SearchFilters()
    t = routing.load().tasks[task]
    messages = [
        {"role": m["role"], "content": [{"text": m["content"]}]}
        for m in history[-HISTORY:]
        if m["role"] in ("user", "assistant") and m["content"]
    ]
    messages.append({"role": "user", "content": [{"text": question}]})
    variables = {
        "today": date.today().isoformat(),
        "max_tool_calls": t.max_tool_calls,
        "scope": scope.model_dump_json(exclude_defaults=True) or "everything",
    }
    async for ev in run_agent(
        task,
        "ask",
        variables,
        lambda r: build_tools(user, scope, r),
        messages,
        documents_restricted=local_only,
        route=route,
    ):
        if ev["type"] != "done":
            yield ev
            continue
        cited = citations(ev["text"], user)
        for c in cited:
            yield {"type": "citation", **c}
        yield ev | {"citations": cited, "uncited": is_uncited(ev["text"], cited)}

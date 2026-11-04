"""Write ai_runs rows. Every model attempt is logged, successful or not."""

import json
from decimal import Decimal
from typing import Any

from docuhive import db
from docuhive.ai.models import AIRun
from docuhive.ai.router import Route

_MAX_OUTPUT = 20_000


def log(
    task: str,
    route: Route | None,
    *,
    restricted: bool,
    prompt_version: str,
    status: str,
    document_id: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: Decimal | None = None,
    latency_ms: int | None = None,
    output: Any = None,
    error: str | None = None,
) -> int:
    if isinstance(output, str) and len(output) > _MAX_OUTPUT:
        output = output[:_MAX_OUTPUT]
    elif output is not None and len(json.dumps(output, default=str)) > _MAX_OUTPUT:
        output = json.dumps(output, default=str)[:_MAX_OUTPUT]
    row = AIRun(
        task=task,
        document_id=document_id,
        # A skipped run never reached a model: nothing left the machine, so it counts as local.
        provider=route.provider if route else "none",
        model=route.model if route else "none",
        local=route.local if route else True,
        restricted=restricted,
        prompt_version=prompt_version,
        status=status,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        output=json.loads(json.dumps(output, default=str)) if output is not None else None,
        error=(error or "")[:2000] or None,
    )
    with db.session() as s:
        s.add(row)
        s.flush()
        return row.id

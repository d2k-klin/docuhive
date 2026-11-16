"""AI for plugins, through DocuHive's harness: privacy rules, budgets, retries and the run log
apply without the plugin doing anything."""

import json
from collections.abc import Callable

from pydantic import BaseModel

from docuhive.contracts import DocumentView

from ._plugin import current


class Unavailable(RuntimeError):
    """No model may answer: AI is off, the document is private and no local model is set up,
    the monthly budget is used up, or every model failed. Show the message and carry on."""


def ask[T: BaseModel](
    prompt: str,
    output: type[T],
    *,
    document: DocumentView | None = None,
    variables: dict | None = None,
    validate: Callable[[T], T] | None = None,
    restricted: bool | None = None,
) -> T:
    """Ask the question in prompts/<prompt>.md and get a typed answer. With `document`, the
    prompt can use {title}, {document_type}, {facts} and {content}."""
    registry = current()
    registry.require("ai")
    try:
        from docuhive.agents import base
        from docuhive.ai.budgets import BudgetExceeded
        from docuhive.ai.privacy import NoAllowedRoute
    except ImportError as error:
        raise Unavailable("AI is not installed on this server") from error
    values: dict = {}
    if document is not None:
        from docuhive import documents

        values = {
            "title": document.title or "",
            "document_type": document.document_type or "",
            "facts": json.dumps(
                {
                    k: v.model_dump(mode="json", exclude_none=True)
                    for k, v in document.facts.items()
                },
                ensure_ascii=False,
            ),
            "content": documents.get_content(document.id, 12000),
        }
    values |= variables or {}
    name = f"{registry.id}.{prompt}"
    try:
        result = base.run_structured(
            name, name, values, output, document=document, validate=validate, restricted=restricted
        )
    except (base.AIDisabled, base.AllRoutesFailed, base.InvalidOutput, NoAllowedRoute) as error:
        raise Unavailable(str(error) or type(error).__name__) from error
    except BudgetExceeded as error:
        raise Unavailable(f"The monthly AI budget is used up: {error}") from error
    return result.value

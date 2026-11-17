"""Plugin screens: page descriptions, each block's data, and actions, for the signed-in user.

Data functions and actions are reachable only through a page that uses them, and only on pages
the user may open; a plugin's data function cannot be called on its own.
"""

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from docuhive import documents
from docuhive.auth import current_user
from docuhive.contracts import CurrentUser
from docuhive.plugins import pages as schema
from docuhive.plugins import runtime
from docuhive.sdk.pages import ActionError, Result

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/plugin-pages", tags=["plugin pages"])
UserDep = Annotated[CurrentUser, Depends(current_user)]
CONTROL = {"sort", "page", "page_size"}


class NavEntry(BaseModel):
    plugin: str
    plugin_name: str
    page: str
    label: Any
    icon: str
    order: int


class SlotEntry(BaseModel):
    plugin: str
    plugin_name: str
    page: str
    description: dict


def _fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message, "details": {}})


def _allowed(page: schema.Page, user: CurrentUser) -> bool:
    allowed = {"member": {"admin", "member", "bookkeeper"}, "bookkeeper": {"admin", "bookkeeper"}}
    return user.role in allowed.get(page.access, {"admin"})


def _page(plugin: str, name: str, user: CurrentUser) -> tuple[Any, schema.Page]:
    loaded = runtime.LOADED.get(plugin)
    page = loaded.registry.pages.get(name) if loaded else None
    if loaded is None or page is None or not _allowed(page, user):
        raise _fail(404, "not_found", "This page does not exist or is not available to you.")
    return loaded, page


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    return value


def cell(row: dict, field: str) -> Any:
    value: Any = row
    for part in field.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    if isinstance(value, dict) and "value" in value and "type" in value:  # a document fact
        return value
    return value


def _scalar(value: Any) -> Any:
    return value["value"] if isinstance(value, dict) and "value" in value else value


def _call(loaded: Any, fn: Any, user: CurrentUser, params: dict) -> Any:
    try:
        return fn(user, params)
    except ActionError:
        raise
    except Exception:
        reference = uuid.uuid4().hex[:8]
        log.exception("Plugin %s failed (reference %s)", loaded.registry.id, reference)
        raise _fail(
            502,
            "plugin_error",
            f"This part of the page could not be loaded (reference {reference}).",
        ) from None


def _documents(user: CurrentUser, spec: schema.DocumentFilter) -> list[dict]:
    from sqlalchemy import select

    from docuhive import auth, db
    from docuhive.contracts import SearchFilters
    from docuhive.db.models import Document
    from docuhive.search.filters import conditions

    def listed(value: str | list[str] | None) -> list[str]:
        return [value] if isinstance(value, str) else list(value or [])

    filters = SearchFilters(
        document_types=listed(spec.document_type), categories=listed(spec.category), tags=spec.tags
    )
    with db.session() as s:
        ids = list(
            s.scalars(
                select(Document.id)
                .where(auth.visible_docs(user), Document.status == "stored", *conditions(filters))
                .limit(2000)  # ponytail: fact conditions run in Python; move to SQL past this
            )
        )
    rows = []
    today = date.today().isoformat()
    for doc_id in ids:
        view = documents.get(doc_id).model_dump(mode="json")
        keep = True
        for fact, rule in spec.facts.items():
            value = (view["facts"].get(fact) or {}).get("value")
            for op, wanted in rule.items():
                wanted = today if wanted == "today" else wanted
                if value is None or (
                    (op == "from" and value < wanted)
                    or (op == "to" and value > wanted)
                    or (op == "equals" and value != wanted)
                ):
                    keep = False
        if keep:
            rows.append(view)
    return rows


def _filtered(rows: list[dict], block: schema.TableBlock, params: dict) -> list[dict]:
    for f in block.filters:
        wanted = params.get(f.field)
        if wanted in (None, ""):
            continue
        if f.type == "text":
            needle = str(wanted).lower()
            if all(cell(r, f.field) is None for r in rows):  # not a column: search them all
                columns = [c.field for c in block.columns]
                rows = [
                    r
                    for r in rows
                    if any(needle in str(_scalar(cell(r, c)) or "").lower() for c in columns)
                ]
            else:
                rows = [r for r in rows if needle in str(_scalar(cell(r, f.field)) or "").lower()]
        elif f.type == "year":
            rows = [r for r in rows if str(_scalar(cell(r, f.field)) or "")[:4] == str(wanted)]
        elif f.type == "boolean":
            rows = [r for r in rows if bool(_scalar(cell(r, f.field))) == (wanted == "true")]
        else:
            rows = [r for r in rows if str(_scalar(cell(r, f.field))) == str(wanted)]
    return rows


def _sorted(rows: list[dict], key: str | None) -> list[dict]:
    if not key:
        return rows
    field, reverse = key.lstrip("-"), key.startswith("-")
    present = [r for r in rows if _scalar(cell(r, field)) not in (None, "")]
    missing = [r for r in rows if _scalar(cell(r, field)) in (None, "")]

    def value(row: dict) -> Any:
        raw = _scalar(cell(row, field))
        try:
            return (0, Decimal(str(raw)))
        except (InvalidOperation, ValueError):
            return (1, str(raw).lower())

    return sorted(present, key=value, reverse=reverse) + missing


def _totals(rows: list[dict], block: schema.TableBlock) -> dict:
    out: dict[str, dict[str, str]] = {}
    for column in block.columns:
        if not column.total:
            continue
        sums: dict[str, Decimal] = {}
        for row in rows:
            raw = cell(row, column.field)
            currency = (raw.get("currency") if isinstance(raw, dict) else row.get("currency")) or (
                "EUR" if column.format == "money" else ""
            )
            try:
                sums[currency] = sums.get(currency, Decimal(0)) + Decimal(str(_scalar(raw)))
            except (InvalidOperation, ValueError):
                continue
        out[column.field] = {k: str(v) for k, v in sums.items()}
    return out


def _options(loaded: Any, user: CurrentUser, items: list[Any], params: dict) -> dict:
    out = {}
    for item in items:
        options = getattr(item, "options", None)
        key = getattr(item, "field", None) or getattr(item, "name", None)
        if isinstance(options, str) and options:
            fn = loaded.registry.data_sources[options]
            out[key] = jsonable(_call(loaded, fn, user, params))
        elif options:
            out[key] = [{"value": o, "label": o} for o in options]
        for column in getattr(item, "columns", None) or []:  # a `lines` field's choice columns
            out |= {f"{key}.{k}": v for k, v in _options(loaded, user, [column], params).items()}
    return out


def _description(loaded: Any, page: schema.Page) -> dict:
    previews = sorted(n for n, (_, f) in loaded.registry.actions.items() if f.get("preview"))
    return {
        "plugin": loaded.registry.id,
        "plugin_name": loaded.manifest.name,
        "previews": previews,  # these actions show what goes out before it is sent
        **page.model_dump(mode="json", by_alias=True, exclude_none=True),
    }


@router.get("/nav", response_model=list[NavEntry])
def nav(user: UserDep) -> list[NavEntry]:
    out = []
    for plugin_id, loaded in runtime.LOADED.items():
        for name, page in loaded.registry.pages.items():
            if page.nav and not name.startswith("_") and _allowed(page, user):
                out.append(
                    NavEntry(
                        plugin=plugin_id,
                        plugin_name=loaded.manifest.name,
                        page=name,
                        label=page.nav.label,
                        icon=page.nav.icon,
                        order=page.nav.order,
                    )
                )
    return sorted(out, key=lambda e: (e.order, e.plugin, e.page))


@router.get("/slots/dashboard", response_model=list[SlotEntry])
def dashboard(user: UserDep) -> list[SlotEntry]:
    return [
        SlotEntry(
            plugin=plugin_id,
            plugin_name=loaded.manifest.name,
            page="_dashboard",
            description=_description(loaded, page),
        )
        for plugin_id, loaded in runtime.LOADED.items()
        if (page := loaded.registry.pages.get("_dashboard")) and _allowed(page, user)
    ]


@router.get("/slots/document/{doc_id}", response_model=list[SlotEntry])
def document_slot(doc_id: str, user: UserDep) -> list[SlotEntry]:
    try:
        view = documents.get_for_user(doc_id, user)
    except documents.NotFound:
        raise _fail(404, "not_found", "Document not found") from None
    out = []
    for plugin_id, loaded in runtime.LOADED.items():
        page = loaded.registry.pages.get("_document")
        if page is None or page.for_ is None or not _allowed(page, user):
            continue
        types, cats = page.for_.document_types, page.for_.categories
        category = view.category or ""
        if (types and view.document_type in types) or any(
            category == c or category.startswith(c + "/") for c in cats
        ):
            out.append(
                SlotEntry(
                    plugin=plugin_id,
                    plugin_name=loaded.manifest.name,
                    page="_document",
                    description=_description(loaded, page),
                )
            )
    return out


@router.get("/{plugin}/{name}")
def page_description(plugin: str, name: str, user: UserDep) -> dict:
    loaded, page = _page(plugin, name, user)
    return _description(loaded, page)


@router.get("/{plugin}/{name}/blocks/{index}")
def block_data(plugin: str, name: str, index: int, request: Request, user: UserDep) -> Any:
    try:
        return _block_data(plugin, name, index, request, user)
    except ActionError as error:  # the plugin's message for the person, such as "choose a book"
        raise _fail(422, "plugin_message", str(error)) from error


def _block_data(plugin: str, name: str, index: int, request: Request, user: CurrentUser) -> Any:
    loaded, page = _page(plugin, name, user)
    if not 0 <= index < len(page.blocks):
        raise _fail(404, "not_found", "No such part of the page")
    block = page.blocks[index]
    params = dict(request.query_params)
    if name == "_document":
        document_slot(params.get("document_id", ""), user)  # the user must see that document
    sources = loaded.registry.data_sources
    if isinstance(block, schema.TableBlock):
        rows = (
            _documents(user, block.documents)
            if block.documents is not None
            else _call(loaded, sources[block.source], user, params)  # type: ignore[index]
        )
        rows = [jsonable(r) for r in rows]
        rows = _sorted(_filtered(rows, block, params), params.get("sort") or block.sort)
        size = min(int(params.get("page_size") or block.page_size), 500)
        first = max(int(params.get("page") or 0), 0) * size
        return {
            "rows": rows[first : first + size],
            "total": len(rows),
            "totals": _totals(rows, block),
            "options": _options(loaded, user, block.filters, params),
        }
    if isinstance(block, schema.FormBlock):
        initial = _call(loaded, sources[block.initial], user, params) if block.initial else {}
        return {
            "initial": jsonable(initial or {}),
            "options": _options(loaded, user, block.fields, params),
        }
    if isinstance(block, (schema.SummaryBlock, schema.StepsBlock, schema.ChartBlock)):
        return {"items": jsonable(_call(loaded, sources[block.source], user, params) or [])}
    if isinstance(block, schema.DetailBlock):
        return {"record": jsonable(_call(loaded, sources[block.source], user, params) or {})}
    return {}


@router.get("/{plugin}/{name}/blocks/{index}/shown")
def block_shown(plugin: str, name: str, index: int, request: Request, user: UserDep) -> dict:
    """Whether a block with `show_if` is shown for these parameters (an invoice still a draft)."""
    loaded, page = _page(plugin, name, user)
    if not 0 <= index < len(page.blocks):
        raise _fail(404, "not_found", "No such part of the page")
    block = page.blocks[index]
    if not block.show_if:
        return {"shown": True}
    try:
        value = _call(
            loaded, loaded.registry.data_sources[block.show_if], user, dict(request.query_params)
        )
    except ActionError:
        return {"shown": False}
    return {"shown": bool(value)}


@router.post("/{plugin}/{name}/actions/{action}/preview")
def preview_action(plugin: str, name: str, action: str, body: dict, user: UserDep) -> Response:
    """Exactly what an outgoing action would send, for the person to check first."""
    loaded, page = _page(plugin, name, user)
    if action not in schema.names(page)[1]:
        raise _fail(404, "not_found", "This action is not on this page")
    preview = loaded.registry.actions[action][1].get("preview")
    if preview is None:
        raise _fail(404, "not_found", "This action has no preview")
    try:
        shown = _call(loaded, preview, user, body)
    except ActionError as error:
        return JSONResponse(
            {"error": {"code": "action_refused", "message": str(error), "details": {}}}, 422
        )
    return JSONResponse(jsonable(shown))


@router.post("/{plugin}/{name}/actions/{action}")
def run_action(plugin: str, name: str, action: str, body: dict, user: UserDep) -> Response:
    loaded, page = _page(plugin, name, user)
    if action not in schema.names(page)[1]:
        raise _fail(404, "not_found", "This action is not on this page")
    if name == "_document":
        document_slot(str(body.get("document_id", "")), user)
    from docuhive.sdk._plugin import INTERACTIVE

    fn, _ = loaded.registry.actions[action]
    flag = INTERACTIVE.set(True)
    try:
        result = _call(loaded, fn, user, body)
    except ActionError as error:
        return JSONResponse(
            {"error": {"code": "action_refused", "message": str(error), "details": {}}}, 422
        )
    finally:
        INTERACTIVE.reset(flag)
    if isinstance(result, Result) and result.download:
        filename, content, media = result.download
        return Response(
            content,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    if isinstance(result, Result) and result.errors:
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_input",
                    "message": result.message or "Check the marked fields.",
                    "details": {"fields": result.errors},
                }
            },
            422,
        )
    message = result.message if isinstance(result, Result) else str(result or "Done.")
    goto = result.goto if isinstance(result, Result) else None
    return JSONResponse({"message": message, "goto": goto})

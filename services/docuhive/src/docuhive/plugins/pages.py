"""Plugin screens described in YAML (`pages/*.yaml`) and drawn by the web app's own components.

The web app knows block types, never plugins. A page that names a data source or an action the
plugin does not register is refused when the plugin starts, so it never fails in front of a user.
"""

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from . import files
from .manifest import ManifestError, load_yaml

Format = Literal[
    "text", "money", "number", "date", "datetime", "percent", "badge", "document", "boolean"
]
Access = Literal["member", "bookkeeper", "admin"]
Text = str | dict[str, str]  # a string, or {language: string}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Link(_Strict):
    page: str | None = None  # another page of this plugin
    params: dict[str, str] = {}  # {param: row field}
    document: str | None = None  # a row field holding a document id


class Column(_Strict):
    field: str
    label: Text = Field(min_length=1)  # a header people (and screen readers) can read
    format: Format = "text"
    align: Literal["left", "right"] | None = None
    total: bool = False  # summed on the server, per currency for money
    link: Link | Literal["document"] | None = None
    tones: dict[str, str] = {}  # badge value -> ok | warn | error | info | muted


class Filter(_Strict):
    field: str
    type: Literal["text", "choice", "year", "date", "boolean"]
    label: Text = ""
    options: list[str] | str = []  # values, or the name of a data source returning [{value, label}]


class DocumentFilter(_Strict):
    """A document listing with no Python: the user's visible documents that match."""

    document_type: str | list[str] | None = None
    category: str | list[str] | None = None
    tags: list[str] = []
    facts: dict[str, dict[str, str]] = {}  # {fact: {from|to|equals: value or "today"}}


class Action(_Strict):
    label: Text
    action: str
    when: str | None = None  # on a row: shown only when this field of the row has a value
    confirm: Text | None = None
    primary: bool = False
    download: bool = False


class BlockBase(_Strict):
    id: str | None = None
    title: Text | None = None
    help: Text | None = None
    show_if: str | None = None  # a data source: the block is shown only when it returns something


class TextBlock(BlockBase):
    type: Literal["text"]
    text: Text


class SummaryBlock(BlockBase):
    type: Literal["summary"]
    source: str


class TableBlock(BlockBase):
    type: Literal["table"]
    source: str | None = None
    documents: DocumentFilter | None = None
    columns: list[Column] = Field(min_length=1)
    filters: list[Filter] = []
    sort: str | None = None
    page_size: int = Field(default=50, ge=5, le=500)
    select: bool = False
    actions: list[Action] = []  # on the selected rows
    row_actions: list[Action] = []  # on one row; the row is sent as params
    copy_column: str | None = None  # a column: a copy button on each value, and "Copy all"
    empty: Text

    @model_validator(mode="after")
    def _copy_is_a_column(self) -> "TableBlock":
        if self.copy_column and self.copy_column not in {c.field for c in self.columns}:
            raise ValueError(
                f"copy_column names '{self.copy_column}', which is not one of the columns"
            )
        return self


class DetailField(_Strict):
    field: str
    label: Text
    format: Format = "text"


class DetailBlock(BlockBase):
    type: Literal["detail"]
    source: str
    fields: list[DetailField] = Field(min_length=1)


class LineColumn(_Strict):
    """One column of a `lines` field: invoice lines, for example."""

    name: str
    label: Text
    type: Literal["text", "number", "money", "choice"] = "text"
    options: list[str] | str = []
    required: bool = False


class FormField(_Strict):
    name: str
    type: Literal[
        "text",
        "textarea",
        "number",
        "money",
        "date",
        "choice",
        "boolean",
        "document",
        "file",
        "lines",
    ]
    columns: list[LineColumn] = []  # for `lines`: the value is a list of {column: value}
    label: Text
    required: bool = False
    options: list[str] | str = []
    help: Text | None = None
    min: float | None = None
    max: float | None = None
    pattern: str | None = None


class FormBlock(BlockBase):
    type: Literal["form"]
    fields: list[FormField] = Field(min_length=1)
    action: str
    initial: str | None = None
    submit: Text = "Save"
    confirm: Text | None = None


class ActionsBlock(BlockBase):
    type: Literal["actions"]
    actions: list[Action] = Field(min_length=1)


class StepsBlock(BlockBase):
    type: Literal["steps"]
    source: str
    empty: Text = "Nothing left to do."


class ChartBlock(BlockBase):
    type: Literal["chart"]
    source: str
    x: str
    y: str
    kind: Literal["bar", "line"] = "bar"
    format: Format = "number"
    empty: Text = "Nothing to show yet."


Block = Annotated[
    TextBlock
    | SummaryBlock
    | TableBlock
    | DetailBlock
    | FormBlock
    | ActionsBlock
    | StepsBlock
    | ChartBlock,
    Field(discriminator="type"),
]


# The icons a plugin page can use in the sidebar (the web app ships only these).
ICONS = (
    "banknote briefcase calculator calendar car chart-column credit-card file-pen file-text fuel "
    "graduation-cap heart-pulse house landmark mail package puzzle receipt scroll-text shield "
    "sofa users wallet"
).split()


class Nav(_Strict):
    label: Text
    icon: str = "puzzle"
    order: int = 50

    @field_validator("icon")
    @classmethod
    def known_icon(cls, value: str) -> str:
        if value not in ICONS:
            raise ValueError(f"'{value}' is not an icon here; use one of: {', '.join(ICONS)}")
        return value


class Slot(_Strict):
    """Where `_document.yaml` appears: documents of these types or categories."""

    document_types: list[str] = []
    categories: list[str] = []


class Page(_Strict):
    title: Text
    description: Text | None = None
    access: Access = "member"
    nav: Nav | None = None
    params: list[str] = []
    for_: Slot | None = Field(default=None, alias="for")
    blocks: list[Block] = Field(min_length=1)


def names(page: Page) -> tuple[set[str], set[str]]:
    """(data sources, actions) a page uses."""
    sources: set[str] = set()
    actions: set[str] = set()
    for block in page.blocks:
        if block.show_if:
            sources.add(block.show_if)
        if isinstance(block, (SummaryBlock, DetailBlock, StepsBlock, ChartBlock)):
            sources.add(block.source)
        if isinstance(block, TableBlock):
            if block.source:
                sources.add(block.source)
            sources |= {
                f.options for f in block.filters if isinstance(f.options, str) and f.options
            }
            actions |= {a.action for a in [*block.actions, *block.row_actions]}
        if isinstance(block, FormBlock):
            actions.add(block.action)
            if block.initial:
                sources.add(block.initial)
            sources |= {f.options for f in block.fields if isinstance(f.options, str) and f.options}
            sources |= {
                c.options
                for f in block.fields
                for c in f.columns
                if isinstance(c.options, str) and c.options
            }
        if isinstance(block, ActionsBlock):
            actions |= {a.action for a in block.actions}
    return sources, actions


def _problems(rel: str, data: Any, error: ValidationError) -> list[str]:
    out = []
    for e in error.errors():
        where = ".".join(str(p) for p in e["loc"] if not str(p).endswith("Block"))
        message = e["msg"].removeprefix("Value error, ")
        if e["type"] == "extra_forbidden":
            message = "is not a known key here (check the spelling)"
        elif e["type"] == "missing":
            message = "is required"
        elif e["type"] == "union_tag_invalid":
            message = (
                "is not a block type; use text, summary, table, detail, form, actions, steps "
                "or chart"
            )
        out.append(f"{rel}: {where} {message}")
    return out


def load(plugin: Path) -> tuple[dict[str, Page], list[str]]:
    """Every page of a plugin (custom/ first), and the problems found."""
    pages: dict[str, Page] = {}
    problems: list[str] = []
    stems = {
        p.stem
        for root in (plugin / "pages", plugin / "custom" / "pages")
        if root.is_dir()
        for p in root.glob("*.yaml")
    }
    for stem in sorted(stems):
        path = files.resolve(plugin, "pages", f"{stem}.yaml")
        if path is None:
            continue
        rel = path.relative_to(plugin).as_posix()
        try:
            data = load_yaml(path)
            pages[stem] = Page.model_validate(data)
        except ManifestError as error:
            problems += [f"{rel}: {p.split(': ', 1)[-1]}" for p in error.problems]
        except ValidationError as error:
            problems += _problems(rel, data, error)
    for stem, page in pages.items():
        if stem == "_document" and page.for_ is None:
            problems.append(f"pages/{stem}.yaml: say which documents it is for, under for:")
        if stem == "_dashboard" and len(page.blocks) != 1:
            problems.append(f"pages/{stem}.yaml: a dashboard card has exactly one block")
    return pages, problems

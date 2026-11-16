"""`plugin.yaml`: what a plugin is and may do, validated with errors a person can act on."""

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from docuhive.sdk.version import __version__ as SDK_VERSION
from docuhive.taxonomy import Contribution

ID = r"^[a-z][a-z0-9-]{1,30}$"
CAPABILITIES = {
    "documents:read": "Read the documents the current user may see",
    "documents:write-metadata": "Change titles, categories, tags and values of documents",
    "documents:create": "Add documents it generates to the archive",
    "documents:hold": "Make documents unchangeable, for example an issued invoice",
    "ai": "Ask an AI model, within your privacy settings and budgets",
    "mail:send": "Send mail when a person asks it to",
    "secrets": "Keep secrets such as passwords or certificates",
}


class ManifestError(ValueError):
    """Every problem in one plugin.yaml, each as `file:line: message`."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


class Network(BaseModel):
    model_config = ConfigDict(extra="forbid")
    network: list[str] = Field(min_length=1)

    @field_validator("network")
    @classmethod
    def hosts(cls, value: list[str]) -> list[str]:
        for host in value:
            if not re.fullmatch(r"(\*\.)?[A-Za-z0-9.-]+(:\d+)?", host):
                raise ValueError(f"'{host}' is not a host name, such as api.example.org")
        return value


class SettingField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")
    type: Literal["string", "number", "boolean", "date", "choice", "secret", "profile"]
    label: str
    help: str = ""
    default: Any = None
    required: bool = False
    options: list[str] = []
    show_if: str | None = None


class SetupCheckSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,40}$")
    title: str
    when_missing: str  # a setting key
    message: str = "Finish this plugin's settings."
    required: bool = False


class AiTask(BaseModel):
    """A prompt in prompts/<prompt>.md becomes the AI task `plugin.<id>.<prompt>`; routing.yaml
    may route it, otherwise it uses the route of `like`."""

    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,40}$")
    like: Literal["classify", "extract", "triage", "chat"] = "extract"


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=ID)
    name: str
    description: str = ""
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    requires_sdk: str
    depends_on: list[str] = []
    capabilities: list[str | Network] = []
    settings: list[SettingField] = []
    setup_checks: list[SetupCheckSpec] = []
    snapshot: bool = False
    taxonomy: Contribution = Contribution()
    ai_tasks: list[AiTask] = []

    @field_validator("capabilities")
    @classmethod
    def known(cls, value: list) -> list:
        for item in value:
            if isinstance(item, str) and item not in CAPABILITIES:
                raise ValueError(f"unknown capability '{item}'; use one of {sorted(CAPABILITIES)}")
        return value

    @field_validator("requires_sdk")
    @classmethod
    def specifier(cls, value: str) -> str:
        parse_specifier(value)
        return value

    def capability_names(self) -> list[str]:
        """Strings for display and for comparing what was granted: `network:host` per host."""
        out: list[str] = []
        for item in self.capabilities:
            if isinstance(item, Network):
                out += [f"network:{host}" for host in item.network]
            else:
                out.append(item)
        return sorted(out)

    def hosts(self) -> list[str]:
        return [h for c in self.capabilities if isinstance(c, Network) for h in c.network]

    def sdk_compatible(self) -> bool:
        return satisfies(SDK_VERSION, self.requires_sdk)


def _version(text: str) -> tuple[int, ...]:
    parts = text.strip().split(".")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"'{text}' is not a version such as 1 or 1.2.0")
    return tuple(int(p) for p in parts) + (0,) * (3 - len(parts))


def parse_specifier(spec: str) -> list[tuple[str, tuple[int, ...]]]:
    # ponytail: >=, >, <=, <, == only; no wildcards or pre-releases, which plugins do not need.
    out = []
    for part in spec.split(","):
        match = re.fullmatch(r"\s*(>=|<=|==|>|<)\s*([\d.]+)\s*", part)
        if not match:
            raise ValueError(f"'{spec}' is not a version range such as \">=1,<2\"")
        out.append((match[1], _version(match[2])))
    return out


def satisfies(version: str, spec: str) -> bool:
    have = _version(version)
    checks = {
        ">=": lambda w: have >= w,
        ">": lambda w: have > w,
        "<=": lambda w: have <= w,
        "<": lambda w: have < w,
        "==": lambda w: have == w,
    }
    return all(checks[op](want) for op, want in parse_specifier(spec))


class _Lines(yaml.SafeLoader):
    """Records the line of every mapping key, so errors can point at it."""


def _mapping(loader: _Lines, node: yaml.MappingNode) -> dict:
    data = loader.construct_mapping(node, deep=True)
    lines = {k.value: k.start_mark.line + 1 for k, _ in node.value if hasattr(k, "value")}
    return _LineDict(data, lines)


class _LineDict(dict):
    def __init__(self, data: dict, lines: dict) -> None:
        super().__init__(data)
        self.lines = lines


_Lines.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_yaml(path: Path) -> Any:
    """YAML with line numbers on mappings; a syntax error names its line."""
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=_Lines)  # noqa: S506 - SafeLoader
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark
        line = f":{mark.line + 1}" if mark else ""
        raise ManifestError([f"{path.name}{line}: {error.problem or error}"]) from None
    except OSError as error:
        raise ManifestError([f"{path.name}: cannot be read ({error.strerror})"]) from None


def _line(data: Any, loc: tuple) -> int | None:
    node, line = data, None
    for key in loc:
        if isinstance(node, _LineDict) and key in node.lines:
            line = node.lines[key]
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            break
    return line


def load(path: Path) -> Manifest:
    """Read `<folder>/plugin.yaml`; the id must equal the folder name."""
    file = path / "plugin.yaml"
    data = load_yaml(file)
    if not isinstance(data, dict):
        raise ManifestError([f"{file.name}: must be a mapping of keys such as id, name, version"])
    try:
        manifest = Manifest.model_validate(data)
    except ValidationError as error:
        problems = []
        for e in error.errors():
            line = _line(data, e["loc"])
            where = f"{file.name}:{line}" if line else file.name
            field = ".".join(str(p) for p in e["loc"]) or "plugin.yaml"
            message = e["msg"].removeprefix("Value error, ")
            if e["type"] == "extra_forbidden":
                message = "is not a known key here (check the spelling)"
            if e["type"] == "missing":
                message = "is required"
            problems.append(f"{where}: {field} {message}")
        raise ManifestError(problems) from None
    if manifest.id != path.name:
        raise ManifestError(
            [f"{file.name}: id '{manifest.id}' must equal the folder name '{path.name}'"]
        )
    return manifest

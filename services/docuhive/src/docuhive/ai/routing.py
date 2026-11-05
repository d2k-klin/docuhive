"""routing.yaml: the validated description of providers, task routes, privacy, budgets, pricing."""

import os
import re
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from docuhive import config

ProviderKind = Literal["ollama", "anthropic", "openai", "bedrock", "litellm", "fake"]


class Provider(BaseModel):
    kind: ProviderKind
    local: bool = False
    enabled: bool = True
    experimental: bool = False
    host: str | None = None  # ollama
    think: bool | None = None  # ollama: reasoning models think first (slow); None = model default
    base_url: str | None = None  # openai-compatible
    prefix: str | None = None  # litellm, e.g. "github_copilot"
    region: str | None = None  # bedrock


class ApplyPolicy(BaseModel):
    auto: bool = False
    threshold: float = Field(default=0.8, ge=0, le=1)
    per_field: dict[str, float] = {}

    def threshold_for(self, field: str) -> float:
        return self.per_field.get(field, self.threshold)


class TaskRoute(BaseModel):
    route: str
    fallback: list[str] = []
    dims: int | None = None  # embed
    batch: int = 32  # embed
    context: dict[str, int] = {}
    apply: ApplyPolicy = ApplyPolicy()
    accept_threshold: float = 0.6  # triage
    max_tool_calls: int = 8  # chat / analyse


class Privacy(BaseModel):
    local_only: bool = False
    classify_unknown_locally: bool = True
    restricted_tags: list[str] = ["private"]
    on_restricted_without_local: Literal["skip", "error"] = "skip"


class Price(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    in_: float = Field(default=0.0, alias="in")
    out: float = 0.0


class Limits(BaseModel):
    timeout_s: dict[str, int] = {}
    retries: int = 2


class RoutingConfig(BaseModel):
    version: int = 1
    providers: dict[str, Provider]
    tasks: dict[str, TaskRoute]
    privacy: Privacy = Privacy()
    budgets: dict[str, float] = {}
    pricing: dict[str, Price] = {}
    limits: Limits = Limits()

    @model_validator(mode="after")
    def routes_name_known_providers(self) -> "RoutingConfig":
        for task, t in self.tasks.items():
            for r in [t.route, *t.fallback]:
                provider, sep, model = r.partition("/")
                if not sep or not model:
                    raise ValueError(f"tasks.{task}: route {r!r} must be '<provider>/<model>'")
                if provider not in self.providers:
                    raise ValueError(f"tasks.{task}: unknown provider {provider!r}")
        return self


_VAR = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _interpolate(value: Any) -> Any:
    if isinstance(value, str):
        return _VAR.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    return value


def parse(raw: dict) -> RoutingConfig:
    try:
        return RoutingConfig.model_validate(_interpolate(raw))
    except ValidationError as e:
        lines = [
            f"  {'.'.join(map(str, err['loc'])) or '<root>'}: {err['msg']}" for err in e.errors()
        ]
        raise ValueError("routing.yaml is invalid:\n" + "\n".join(lines)) from None


@lru_cache
def load() -> RoutingConfig:
    return parse(config.load_yaml("routing.yaml"))


def reload() -> None:
    load.cache_clear()

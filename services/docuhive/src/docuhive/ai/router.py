"""Task -> ordered routes (primary, fallbacks), filtered by privacy; route -> Strands model."""

import logging
import os
from dataclasses import dataclass
from typing import Any

from docuhive.ai import routing
from docuhive.ai.settings import get_ai_settings

log = logging.getLogger(__name__)


class ProviderUnavailable(Exception):
    """A provider's optional dependency is missing or the provider is misconfigured."""


@dataclass(frozen=True)
class Route:
    provider: str  # key in routing.providers
    model: str
    local: bool

    def __str__(self) -> str:
        return f"{self.provider}/{self.model}"


def parse_route(spec: str, cfg: routing.RoutingConfig | None = None) -> Route:
    cfg = cfg or routing.load()
    provider, _, model = spec.partition("/")
    return Route(provider, model, cfg.providers[provider].local)


def resolve(task: str, *, restricted: bool) -> list[Route]:
    """Primary then fallbacks. Restricted input or local_only keeps only local routes."""
    cfg = routing.load()
    t = cfg.tasks.get(task)
    if t is None:
        return []
    out: list[Route] = []
    for spec in [t.route, *t.fallback]:
        route = parse_route(spec, cfg)
        p = cfg.providers[route.provider]
        if not p.enabled or route in out:
            continue
        if p.kind == "fake" and os.environ.get("DOCUHIVE_ENV") != "test":
            continue
        if (restricted or cfg.privacy.local_only) and not route.local:
            continue
        out.append(route)
    return out


_MODELS: dict[Route, Any] = {}
_warned_experimental: set[str] = set()


def model_for(route: Route) -> Any:
    """A cached Strands model for the route. Imports are lazy so `ai` stays an optional extra."""
    if route in _MODELS:
        return _MODELS[route]
    p = routing.load().providers[route.provider]
    if p.experimental and route.provider not in _warned_experimental:
        _warned_experimental.add(route.provider)
        log.warning("Provider %s is experimental and unofficial for this use", route.provider)
    s = get_ai_settings()
    try:
        if p.kind == "fake":
            from docuhive.ai.fake import model_for_route

            m: Any = model_for_route(route)
        elif p.kind == "ollama":
            from strands.models.ollama import OllamaModel

            extra = {"think": p.think} if p.think is not None else None
            m = OllamaModel(p.host or s.ollama_host, model_id=route.model, additional_args=extra)
        elif p.kind == "anthropic":
            from strands.models.anthropic import AnthropicModel

            key = s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else None
            m = AnthropicModel(client_args={"api_key": key}, model_id=route.model, max_tokens=4096)
        elif p.kind == "openai":
            from strands.models.openai import OpenAIModel

            args: dict[str, Any] = {"base_url": p.base_url or s.openai_base_url}
            if s.openai_api_key:
                args["api_key"] = s.openai_api_key.get_secret_value()
            m = OpenAIModel(client_args=args, model_id=route.model)
        elif p.kind == "bedrock":
            from strands.models.bedrock import BedrockModel

            m = BedrockModel(model_id=route.model, region_name=p.region or s.aws_region)
        elif p.kind == "litellm":
            from strands.models.litellm import LiteLLMModel

            prefix = f"{p.prefix}/" if p.prefix else ""
            m = LiteLLMModel(model_id=f"{prefix}{route.model}")
        else:  # pragma: no cover - guarded by the RoutingConfig Literal
            raise ProviderUnavailable(f"unknown provider kind {p.kind}")
    except ImportError as e:
        raise ProviderUnavailable("pip install docuhive[ai]") from e
    _MODELS[route] = m
    return m


def clear_cache() -> None:
    _MODELS.clear()

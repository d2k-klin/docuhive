"""Embeddings: Strands has no embeddings API, so this is a tiny client per provider kind.

One embedder serves the whole index (documents and queries must share a vector space):
the first allowed route of tasks.embed. Restricted documents are embedded only if that
embedder is local; otherwise they stay out of semantic search (FTS still finds them).
"""

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass

import httpx

from docuhive.ai import router, routing, runs
from docuhive.ai.router import ProviderUnavailable, Route
from docuhive.ai.settings import get_ai_settings


@dataclass
class Embedder:
    route: Route
    dims: int
    batch: int = 32

    def embed(
        self, texts: list[str], *, document_id: str | None = None, restricted: bool = False
    ) -> list[list[float]]:
        """Batch, order-preserving. Every batch call is logged to ai_runs (task=embed)."""
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch):
            chunk = texts[i : i + self.batch]
            t0 = time.monotonic()
            try:
                vectors, tokens = _call(self.route, chunk)
            except Exception as e:
                runs.log(
                    "embed",
                    self.route,
                    restricted=restricted,
                    prompt_version="embed@-",
                    status="error",
                    document_id=document_id,
                    error=f"{type(e).__name__}: {e}",
                    latency_ms=int((time.monotonic() - t0) * 1000),
                )
                raise
            runs.log(
                "embed",
                self.route,
                restricted=restricted,
                prompt_version="embed@-",
                status="ok",
                document_id=document_id,
                tokens_in=tokens,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            out += vectors
        return out


def embedder() -> Embedder | None:
    """None if no embedding route is allowed (e.g. local_only with a cloud embedder)."""
    routes = router.resolve("embed", restricted=False)
    if not routes:
        return None
    t = routing.load().tasks["embed"]
    return Embedder(routes[0], t.dims or 1024, t.batch)


def _call(route: Route, texts: list[str]) -> tuple[list[list[float]], int | None]:
    p = routing.load().providers[route.provider]
    s = get_ai_settings()
    if p.kind == "fake":
        return [hashed(t, routing.load().tasks["embed"].dims or 1024) for t in texts], None
    if p.kind == "ollama":
        r = httpx.post(
            f"{(p.host or s.ollama_host).rstrip('/')}/api/embed",
            json={"model": route.model, "input": texts},
            timeout=120,
        )
        r.raise_for_status()
        body = r.json()
        return body["embeddings"], body.get("prompt_eval_count")
    if p.kind == "openai":
        base = (p.base_url or s.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        key = s.openai_api_key.get_secret_value() if s.openai_api_key else ""
        r = httpx.post(
            f"{base}/embeddings",
            json={"model": route.model, "input": texts},
            headers={"Authorization": f"Bearer {key}"},
            timeout=120,
        )
        r.raise_for_status()
        body = r.json()
        data = sorted(body["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data], body.get("usage", {}).get("prompt_tokens")
    if p.kind == "bedrock":
        import boto3  # type: ignore[import-untyped]

        client = boto3.client("bedrock-runtime", region_name=p.region or s.aws_region)
        if "cohere" in route.model:
            resp = client.invoke_model(
                modelId=route.model,
                body=json.dumps({"texts": texts, "input_type": "search_document"}),
            )
            return json.loads(resp["body"].read())["embeddings"], None
        vectors = []
        for t in texts:  # Titan v2 embeds one text per call
            resp = client.invoke_model(modelId=route.model, body=json.dumps({"inputText": t}))
            vectors.append(json.loads(resp["body"].read())["embedding"])
        return vectors, None
    raise ProviderUnavailable(f"provider kind {p.kind} has no embeddings client")


def hashed(text: str, dims: int) -> list[float]:
    """Deterministic bag-of-words vector (the hashing trick): texts sharing words are close.
    Used by `kind: fake` for tests, examples and the eval smoke run. Not semantic."""
    v = [0.0] * dims
    for word in re.findall(r"\w{3,}", text.casefold()):
        h = int.from_bytes(hashlib.blake2b(word[:6].encode(), digest_size=4).digest(), "big")
        v[h % dims] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0

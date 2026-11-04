"""Deterministic HTTP boundaries. No provider credentials, no external forwarding."""

import hashlib
import json
import math
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

ROOT = Path(__file__).resolve().parents[2]


def create_app() -> FastAPI:
    app = FastAPI()
    scripts = json.loads((ROOT / "tests/mocks/scripts.json").read_text())
    captures: list[dict] = []
    app.state.captures = captures

    def record(body: dict, provider: str) -> None:
        canonical = json.dumps(body, sort_keys=True)
        entry = {
            "provider": provider,
            "model": body.get("model"),
            "prompt_sha": hashlib.sha256(canonical.encode()).hexdigest(),
            "body": body,
        }
        captures.append(entry)
        destination = os.environ.get("QA_CAPTURE_LOG")
        if destination:
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as output:
                output.write(json.dumps(entry) + "\n")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/__calls")
    def calls() -> list[dict]:
        return captures

    @app.post("/v1/{endpoint:path}")
    async def llm(endpoint: str, request: Request):
        if endpoint not in {"chat/completions", "messages", "embeddings"}:
            raise HTTPException(404)
        body = await request.json()
        record(body, "anthropic" if endpoint == "messages" else "openai")
        upstream = os.environ.get("QA_LLM_UPSTREAM")
        if upstream:
            # Only the compose fake is supported; never forward to an arbitrary host.
            if upstream != "http://fake-llm:8000":
                raise HTTPException(503, "Unsupported QA upstream")
            async with httpx.AsyncClient(trust_env=False) as client:
                response = await client.post(f"{upstream}/v1/{endpoint}", json=body)
            return Response(
                response.content,
                response.status_code,
                media_type=response.headers.get("content-type"),
            )
        model = body.get("model")
        if endpoint == "embeddings":
            if model != "qa-embed":
                raise HTTPException(400, "Unknown scripted model")
            texts = body.get("input", [])
            texts = [texts] if isinstance(texts, str) else texts
            vectors = []
            for i, text in enumerate(texts):
                raw = hashlib.sha256(text.encode()).digest()
                vector = [(raw[n % len(raw)] - 127.5) / 127.5 for n in range(1024)]
                norm = math.sqrt(sum(v * v for v in vector))
                vectors.append(
                    {"object": "embedding", "index": i, "embedding": [v / norm for v in vector]}
                )
            return {
                "object": "list",
                "model": model,
                "data": vectors,
                "usage": {"prompt_tokens": 10, "total_tokens": 10},
            }
        if model not in scripts:
            raise HTTPException(400, "Unknown scripted model")
        value = scripts[model]
        tools = body.get("tools", [])
        text = value if isinstance(value, str) else json.dumps(value)
        if endpoint == "messages":
            content = [{"type": "text", "text": text}]
            if tools and not isinstance(value, str):
                content = [
                    {"type": "tool_use", "id": "qa_tool", "name": tools[-1]["name"], "input": value}
                ]
            return {
                "id": "qa_message",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": content,
                "stop_reason": "tool_use" if tools else "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 10},
            }
        message = {"role": "assistant", "content": text}
        if tools and not isinstance(value, str):
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "qa_tool",
                        "type": "function",
                        "function": {"name": tools[-1]["function"]["name"], "arguments": text},
                    }
                ],
            }
        result = {
            "id": "qa_completion",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "tool_calls" if "tool_calls" in message else "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }
        if body.get("stream"):
            delta = {k: v for k, v in message.items() if k != "role"}
            if "tool_calls" in delta:
                delta["tool_calls"][0]["index"] = 0
            chunk = {
                **result,
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            end = {
                **chunk,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": result["choices"][0]["finish_reason"],
                    }
                ],
            }
            return StreamingResponse(
                iter(
                    [
                        f"data: {json.dumps(chunk)}\n\n",
                        f"data: {json.dumps(end)}\n\n",
                        "data: [DONE]\n\n",
                    ]
                ),
                media_type="text/event-stream",
            )
        return result

    @app.post("/oauth/token")
    def token() -> dict:
        return {
            "access_token": "synthetic-qa-access",
            "refresh_token": "synthetic-qa-refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    @app.api_route("/mail/{provider}/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
    async def mail(provider: str, path: str, request: Request):
        if provider not in {"gmail", "graph"}:
            raise HTTPException(404)
        record(
            {"method": request.method, "path": path, "query": dict(request.query_params)}, provider
        )
        if request.method != "GET":
            raise HTTPException(405, "Read-only synthetic mailbox")
        fixtures = ROOT / "services/docuhive/tests/intel/fixtures" / provider
        if path == "messages":
            page = (
                "2"
                if request.query_params.get("pageToken") or request.query_params.get("$skiptoken")
                else "1"
            )
            name = f"list_page{page}.json"
        elif provider == "gmail" and path == "messages/m1/attachments/a1":
            name = "attachment_pdf.json"
        elif provider == "gmail" and path == "messages/m1":
            name = "message_m1.json"
        elif provider == "graph" and path in {"messages/g1", "messages/g1/attachments"}:
            name = "attachments_g1.json" if path.endswith("attachments") else "message_g1.json"
        elif provider == "graph" and path.startswith("mailFolders/"):
            return {"id": "deleted-id" if path.endswith("deleteditems") else "junk-id"}
        else:
            raise HTTPException(404)
        data = json.loads((fixtures / name).read_text())
        if "@odata.nextLink" in data:
            data["@odata.nextLink"] = str(request.url).split("?")[0] + "?$skiptoken=abc"
        return JSONResponse(data)

    @app.post("/ntfy/{topic}")
    async def notify(topic: str, request: Request) -> dict:
        record({"topic": topic, "text": (await request.body()).decode()}, "ntfy")
        return {"id": "qa_notification"}

    return app

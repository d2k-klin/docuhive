"""FakeModel: a scripted Strands model for tests, examples and the eval smoke run. No network.

    FakeModel(outputs={"*": {...}})              structured output for every call
    FakeModel(outputs={"Stadtwerke": {...}})     keyed by a substring of the prompt
    FakeModel(outputs={"*": [bad, good]})        consumed in order, the last one sticks
    FakeModel(outputs={"*": lambda prompt: {...}})
    FakeModel(script=[{"tool": "query_facts", "input": {...}}, {"text": "Answer [doc:01J]"}])
    FakeModel(fail=["timeout", "error"])          raise before answering, one per call
Every call is recorded in `.calls` (system prompt + text), so privacy tests can assert what a
model saw.
"""

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from strands.models.model import Model

Output = dict | list | Callable[[str], dict]


class FakeModel(Model):
    def __init__(
        self,
        outputs: dict[str, Output] | None = None,
        script: list[dict] | None = None,
        fail: list[str] | None = None,
        tokens: tuple[int, int] = (100, 20),
    ):
        self.outputs = outputs or {}
        self.script = list(script or [])
        self.fail = list(fail or [])
        self.tokens = tokens
        self.calls: list[dict] = []

    def get_config(self) -> dict:
        return {"model_id": "fake"}

    def update_config(self, **model_config: Any) -> None:
        pass

    async def structured_output(  # type: ignore[override]
        self, output_model: Any, prompt: Any, system_prompt: str | None = None, **kw: Any
    ) -> AsyncIterator:
        raise NotImplementedError("Strands uses the output tool via stream()")
        yield {}  # pragma: no cover

    def seen_text(self) -> str:
        return "\n".join(c["text"] for c in self.calls)

    def _pick(self, text: str) -> dict:
        key = next((k for k in self.outputs if k != "*" and k in text), "*")
        if key not in self.outputs:
            raise KeyError(f"FakeModel has no output for this prompt (keys: {list(self.outputs)})")
        out = self.outputs[key]
        if callable(out):
            return out(text)
        if isinstance(out, list):
            return out.pop(0) if len(out) > 1 else out[0]
        return out

    async def stream(  # type: ignore[override]
        self,
        messages: list,
        tool_specs: list | None = None,
        system_prompt: str | None = None,
        **kw: Any,
    ) -> AsyncIterator:
        text = "\n".join(
            str(block.get("text") or block.get("toolResult") or "")
            for m in messages
            for block in m["content"]
        )
        self.calls.append({"system": system_prompt or "", "text": text, "tools": tool_specs})
        if self.fail:
            kind = self.fail.pop(0)
            raise TimeoutError("fake timeout") if kind == "timeout" else RuntimeError("fake 503")
        output_tool = next(
            (
                t["name"]
                for t in tool_specs or []
                if "StructuredOutputTool" in t.get("description", "")
            ),
            None,
        )
        if output_tool:  # structured output: answer through Strands' output tool
            step = {"tool": output_tool, "input": self._pick(text)}
        elif self.script:  # agent loop: scripted tool calls, then a text answer
            step = self.script.pop(0)
        else:
            step = {"text": "OK"}
        yield {"messageStart": {"role": "assistant"}}
        if "text" in step:
            yield {"contentBlockStart": {"start": {}}}
            for word in step["text"].split(" "):  # stream word by word, like a real model
                yield {"contentBlockDelta": {"delta": {"text": word + " "}}}
            yield {"contentBlockStop": {}}
        if "tool" in step:
            use = {"name": step["tool"], "toolUseId": f"t{len(self.calls)}"}
            yield {"contentBlockStart": {"start": {"toolUse": use}}}
            yield {
                "contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(step["input"])}}}
            }
            yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use" if "tool" in step else "end_turn"}}
        usage = {"inputTokens": self.tokens[0], "outputTokens": self.tokens[1]}
        usage["totalTokens"] = sum(self.tokens)
        yield {"metadata": {"usage": usage, "metrics": {"latencyMs": 1}}}


# Instances for `kind: fake` providers in routing.yaml, keyed by "provider/model".
REGISTRY: dict[str, FakeModel] = {}


def model_for_route(route: Any) -> FakeModel:
    return REGISTRY.setdefault(str(route), FakeModel())

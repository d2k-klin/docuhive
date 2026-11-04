"""CL: AI providers, routing, privacy gate, budgets, ai_runs. See docs/learn/04-agent-harness.md."""


def startup() -> None:
    from docuhive.ai.startup import startup as _startup

    _startup()

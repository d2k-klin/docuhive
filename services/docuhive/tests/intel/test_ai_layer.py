from datetime import UTC, datetime
from decimal import Decimal

import pytest
from docuhive import config, taxonomy
from docuhive.agents import base
from docuhive.ai import budgets, privacy, router, routing, runs
from docuhive.ai.models import AIRun
from docuhive.ai.router import Route
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from tests.fakes.intel import use_routing


class Out(BaseModel):
    title: str
    n: int


@pytest.fixture
def prompt(monkeypatch):
    monkeypatch.setattr(base, "render", lambda name, v: (f"Hello {v['name']}", f"{name}@1"))


def test_routing_rejects_unknown_provider_with_path():
    with pytest.raises(ValueError, match="tasks.classify: unknown provider 'nope'"):
        routing.parse({"providers": {}, "tasks": {"classify": {"route": "nope/x"}}})


def test_default_routing_yaml_is_valid(monkeypatch):
    monkeypatch.setenv("DOCUHIVE_AI_OLLAMA_HOST", "http://nas:11434")
    cfg = routing.parse(config.load_yaml("routing.yaml"))
    assert cfg.providers["ollama"].host == "http://nas:11434"
    assert cfg.providers["copilot"].enabled is False
    assert cfg.tasks["classify"].apply.auto is False
    assert cfg.providers["ollama"].think is False


@pytest.mark.parametrize(("think", "sent"), [(False, {"think": False}), (None, None)])
def test_ollama_think_setting_reaches_the_request(monkeypatch, think, sent):
    pytest.importorskip("strands.models.ollama")
    use_routing(
        monkeypatch, providers={"ollama": {"kind": "ollama", "local": True, "think": think}}
    )
    router._MODELS.clear()
    model = router.model_for(Route("ollama", "qwen3:8b", True))
    assert model.config.get("additional_args") == sent
    router._MODELS.clear()


def test_resolve_orders_and_filters(core, monkeypatch):
    use_routing(monkeypatch, tasks={"chat": {"route": "cloud/m", "fallback": ["local/m"]}})
    assert [str(r) for r in router.resolve("chat", restricted=False)] == ["cloud/m", "local/m"]
    assert [str(r) for r in router.resolve("chat", restricted=True)] == ["local/m"]
    use_routing(
        monkeypatch,
        tasks={"chat": {"route": "cloud/m", "fallback": ["local/m"]}},
        privacy={"local_only": True},
    )
    assert [str(r) for r in router.resolve("chat", restricted=False)] == ["local/m"]


def test_disabled_provider_is_skipped(core, monkeypatch):
    use_routing(
        monkeypatch,
        providers={
            "local": {"kind": "fake", "local": True},
            "cloud": {"kind": "fake", "enabled": False},
        },
        tasks={"chat": {"route": "cloud/m", "fallback": ["local/m"]}},
    )
    assert [str(r) for r in router.resolve("chat", restricted=False)] == ["local/m"]


def test_restricted_category_child_and_tag(core):
    tax = taxonomy.load()
    assert privacy.restricted_category("health/medical", tax)
    assert privacy.restricted_category("government/identity", tax)
    assert not privacy.restricted_category("utilities/electricity", tax)
    d1 = core.docs.get(core.docs.add("x", category="insurance/health"))
    d2 = core.docs.get(core.docs.add("y", category="utilities", tags=["private"]))
    d3 = core.docs.get(core.docs.add("z", category="utilities"))
    assert privacy.is_restricted(d1, tax) and privacy.is_restricted(d2, tax)
    assert not privacy.is_restricted(d3, tax)
    unclassified = core.docs.get(core.docs.add("w"))
    assert privacy.must_stay_local("classify", unclassified, tax)
    assert not privacy.must_stay_local("extract", unclassified, tax)


def test_run_structured_happy_path_logs_run(core, fake, prompt):
    m = fake(outputs={"*": {"title": "t", "n": 1}})
    res = base.run_structured("classify", "p", {"name": "world"}, Out)
    assert res.value == Out(title="t", n=1) and res.prompt_version == "p@1"
    assert "Hello world" in m.seen_text()
    [row] = core.rows("ai_runs")
    assert row["status"] == "ok" and row["tokens_in"] == 100 and row["local"]
    assert row["output"] == {"title": "t", "n": 1} and row["id"] == res.ai_run_id


def test_validation_retry_succeeds(core, fake, prompt):
    m = fake(outputs={"*": [{"title": "bad", "n": 1}, {"title": "good", "n": 2}]})

    def validate(v: Out) -> Out:
        if v.title == "bad":
            raise ValueError("title must not be 'bad'")
        return v

    res = base.run_structured("classify", "p", {"name": "x"}, Out, validate=validate)
    assert res.value.title == "good"
    assert "Your previous answer was invalid: title must not be 'bad'" in m.calls[1]["text"]
    assert [r["status"] for r in core.rows("ai_runs")] == ["invalid", "ok"]


def test_second_invalid_raises(core, fake, prompt):
    fake(outputs={"*": {"title": "bad", "n": 1}})

    def validate(v: Out) -> Out:
        raise ValueError("never valid")

    with pytest.raises(base.InvalidOutput):
        base.run_structured("classify", "p", {"name": "x"}, Out, validate=validate)
    assert [r["status"] for r in core.rows("ai_runs")] == ["invalid", "invalid"]


def test_timeout_falls_back_to_next_route(core, fake, prompt, monkeypatch):
    use_routing(monkeypatch, tasks={"chat": {"route": "cloud/m", "fallback": ["local/m"]}})
    fake("cloud/m", outputs={"*": {"title": "c", "n": 1}}, fail=["timeout", "timeout"])
    fake("local/m", outputs={"*": {"title": "l", "n": 1}})
    res = base.run_structured("chat", "p", {"name": "x"}, Out)
    assert str(res.route) == "local/m"
    assert [(r["provider"], r["status"]) for r in core.rows("ai_runs")] == [
        ("cloud", "timeout"),
        ("cloud", "timeout"),
        ("local", "ok"),
    ]


def test_restricted_doc_with_only_cloud_routes_never_calls_model(core, fake, prompt, monkeypatch):
    use_routing(monkeypatch, tasks={"extract": {"route": "cloud/m"}})
    m = fake("cloud/m", outputs={"*": {"title": "t", "n": 1}})
    doc = core.docs.get(core.docs.add("secret diagnosis", category="health"))
    with pytest.raises(base.NoAllowedRoute):
        base.run_structured("extract", "p", {"name": "x"}, Out, document=doc)
    assert m.calls == []
    [row] = core.rows("ai_runs")
    assert row["status"] == "skipped" and row["restricted"] and row["local"]


def test_cost_from_pricing_and_budget_skip(core, fake, prompt, monkeypatch):
    use_routing(monkeypatch, tasks={"chat": {"route": "cloud/m", "fallback": ["local/m"]}})
    cloud = fake("cloud/m", outputs={"*": {"title": "c", "n": 1}})
    fake("local/m", outputs={"*": {"title": "l", "n": 1}})
    first = base.run_structured("chat", "p", {"name": "x"}, Out)
    assert str(first.route) == "cloud/m"
    # 100 in + 20 out tokens at $1000 per 1M each = $0.12
    assert core.rows("ai_runs")[0]["cost_usd"] == Decimal("0.12")
    for _ in range(8):  # spend $1.08 in total, over the $1 cap
        runs.log(
            "chat",
            Route("cloud", "m", False),
            restricted=False,
            prompt_version="p@1",
            status="ok",
            cost_usd=Decimal("0.12"),
        )
    second = base.run_structured("chat", "p", {"name": "x"}, Out)
    assert str(second.route) == "local/m" and len(cloud.calls) == 1
    log = core.rows("notification_log")
    assert {r["dedupe_key"] for r in log} >= {f"budget:cloud:{datetime.now(UTC):%Y-%m}:100"}


def test_budget_exceeded_when_only_cloud(core, fake, prompt, monkeypatch):
    use_routing(monkeypatch, tasks={"chat": {"route": "cloud/m"}})
    runs.log(
        "chat",
        Route("cloud", "m", False),
        restricted=False,
        prompt_version="p@1",
        status="ok",
        cost_usd=Decimal("5"),
    )
    with pytest.raises(budgets.BudgetExceeded):
        base.run_structured("chat", "p", {"name": "x"}, Out)


def test_month_boundaries():
    dec = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
    assert budgets.month_start(dec) == datetime(2026, 12, 1, tzinfo=UTC)
    assert budgets.next_month_start(dec) == datetime(2027, 1, 1, tzinfo=UTC)


def test_db_check_rejects_restricted_cloud_run(core):
    with pytest.raises(IntegrityError), core.session() as s:
        s.add(
            AIRun(
                task="x",
                provider="cloud",
                model="m",
                local=False,
                restricted=True,
                prompt_version="p@1",
                status="ok",
            )
        )


def test_ai_disabled(core, prompt, monkeypatch):
    from docuhive.ai import settings

    monkeypatch.setattr(settings.get_ai_settings(), "enabled", False)
    with pytest.raises(base.AIDisabled):
        base.run_structured("classify", "p", {"name": "x"}, Out)

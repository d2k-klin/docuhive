import pytest

from tests.fakes.intel import REGISTRY, FakeCore, FakeModel, use_routing


@pytest.fixture
def core(monkeypatch, tmp_path):
    """Fresh fakes for every test: SQLite DB, jobs, documents, ingest, auth, search, routing."""
    from docuhive import taxonomy
    from docuhive.agents import base
    from docuhive.ai import router

    monkeypatch.setenv("DOCUHIVE_ENV", "test")
    monkeypatch.setattr(base, "BACKOFF_S", 0)
    REGISTRY.clear()
    router.clear_cache()
    taxonomy.reload()
    c = FakeCore(tmp_path).install(monkeypatch)
    use_routing(monkeypatch)
    yield c
    REGISTRY.clear()
    router.clear_cache()


@pytest.fixture
def fake(core):
    """fake("local/m", outputs=...) registers a FakeModel for a route and returns it."""

    from docuhive.ai import router

    def make(route: str = "local/m", **kw) -> FakeModel:
        router.clear_cache()
        REGISTRY[route] = FakeModel(**kw)
        return REGISTRY[route]

    return make

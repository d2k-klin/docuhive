"""Route contracts and setup checks, inspected on the real app."""

import pytest
from docuhive.api.app import create_app
from docuhive.contracts import SetupCheck
from fastapi.routing import APIRoute
from qa_plugin import ROOT

PREFIXES = {
    "auth",
    "users",
    "tokens",
    "documents",
    "upload",
    "search",
    "vocabulary",
    "system",
    "taxonomy",
    "ai",
    "review",
    "sources",
    "chat",
    "analyses",
    "reminders",
    "notifications",
}


def test_all_registered_routes_have_owned_prefixes():
    for route in create_app().routes:
        if isinstance(route, APIRoute):
            assert route.path.startswith("/api/")
            assert route.path.split("/")[2] in PREFIXES, route.path


class MissingSetupEndpoint(Exception):
    pass


@pytest.mark.parametrize(
    "area",
    [
        "system",
        "ai",
        "sources",
        "notifications",
    ],
)
@pytest.mark.integration
@pytest.mark.system
@pytest.mark.req("GUIDE-02")
def test_setup_checks_have_actionable_states(area, alice):
    response = alice.get(f"/api/{area}/setup-status")
    if response.status_code == 404:
        raise MissingSetupEndpoint(area)
    assert response.status_code == 200
    checks = [SetupCheck.model_validate(item) for item in response.json()]
    assert checks
    for check in checks:
        if check.required and check.status != "ok":
            assert check.action_label and check.action_href
        if check.help_doc:
            assert (ROOT / check.help_doc).is_file()


def test_boundary_modules_cover_each_current_private_module():
    # Imports are checked by import-linter; this protects its config from a typo.
    import configparser

    config = configparser.ConfigParser()
    config.read(ROOT / ".importlinter")
    for section in config.sections()[1:]:
        for field in ("source_modules", "forbidden_modules"):
            for module in config[section][field].split():
                location = ROOT / "services/docuhive/src" / module.replace(".", "/")
                assert location.with_suffix(".py").is_file() or (location / "__init__.py").is_file()

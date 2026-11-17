"""Plugin platform, part 1: manifest, discovery, custom files, check, loading, CLI, HTTP limits."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from docuhive import config
from docuhive.plugins import check, cli, discovery, files, runtime, state
from docuhive.plugins.manifest import ManifestError, load, satisfies
from docuhive.sdk import http

ROOT = Path(__file__).resolve().parents[4]
EXAMPLES = ROOT / "plugins-example"


def write(folder: Path, manifest: str, extra: dict[str, str] | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plugin.yaml").write_text(manifest)
    (folder / "README.md").write_text("# test\n")
    for name, content in (extra or {}).items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return folder


def basic(plugin_id: str, extra: str = "") -> str:
    return f'id: {plugin_id}\nname: {plugin_id}\nversion: 0.1.0\nrequires_sdk: ">=1,<2"\n{extra}'


@pytest.fixture
def plugins_dir(monkeypatch, tmp_path):
    root = tmp_path / "plugins"
    root.mkdir()
    monkeypatch.setenv("DOCUHIVE_PLUGINS_DIR", str(root))
    config.reload()
    runtime.reset()
    yield root
    runtime.reset()
    config.reload()


def test_manifest_errors_name_the_line(tmp_path):
    folder = write(
        tmp_path / "bad",
        "id: bad\nname: Bad\nversion: one\nrequires_sdk: '>=1'\ncapabilites: []\n"
        "capabilities: [teleport]\n",
    )
    with pytest.raises(ManifestError) as error:
        load(folder)
    text = "\n".join(error.value.problems)
    assert "plugin.yaml:3: version" in text
    assert "plugin.yaml:5: capabilites is not a known key here" in text
    assert "unknown capability 'teleport'" in text
    write(tmp_path / "other", basic("not-other"))
    with pytest.raises(ManifestError, match="must equal the folder name"):
        load(tmp_path / "other")
    write(tmp_path / "syntax", "id: [unclosed\n")
    with pytest.raises(ManifestError, match=r"plugin.yaml:\d"):
        load(tmp_path / "syntax")


def test_version_ranges():
    assert satisfies("1.0.0", ">=1,<2") and not satisfies("2.0.0", ">=1,<2")
    assert satisfies("1.4.2", "==1.4.2") and not satisfies("0.9.9", ">=1")
    with pytest.raises(ValueError):
        satisfies("1.0.0", "~1")


def test_examples_are_valid_plugins():
    for folder in sorted(p for p in EXAMPLES.iterdir() if (p / "plugin.yaml").is_file()):
        assert check.check(folder) == [], folder.name


def test_discovery_order_dependencies_and_compatibility(plugins_dir, tmp_path):
    write(plugins_dir / "base", basic("base"))
    write(plugins_dir / "top", basic("top", "depends_on: [base]\n"))
    write(plugins_dir / "orphan", basic("orphan", "depends_on: [missing]\n"))
    write(plugins_dir / "loop-a", basic("loop-a", "depends_on: [loop-b]\n"))
    write(plugins_dir / "loop-b", basic("loop-b", "depends_on: [loop-a]\n"))
    write(plugins_dir / "future", basic("future").replace(">=1,<2", ">=2"))
    write(plugins_dir / "parked.disabled", basic("parked.disabled"))
    elsewhere = write(tmp_path / "elsewhere", basic("linked"))
    (plugins_dir / "linked").symlink_to(elsewhere)
    found = {f.id: f for f in discovery.discover()}
    assert "linked" not in found and "parked.disabled" not in found
    order = [f.id for f in discovery.discover()]
    assert order.index("base") < order.index("top")
    assert found["top"].loadable
    assert "not installed" in found["orphan"].problems[0]
    assert any("loop" in p for p in found["loop-a"].problems + found["loop-b"].problems)
    assert "Needs a newer DocuHive" in found["future"].problems[0]


def test_custom_files_win_and_rules_can_merge(tmp_path):
    folder = write(
        tmp_path / "p",
        basic("p"),
        {
            "rules/accounts.yaml": (
                "accounts:\n  - {id: '4930', name: Office}\n  - {id: '4200', name: Rent}\n"
                "rate: 19\n"
            ),
            "templates/letter.md": "Plugin wording",
        },
    )
    assert files.read_text(folder, "templates", "letter.md") == "Plugin wording"
    (folder / "custom" / "templates").mkdir(parents=True)
    (folder / "custom" / "templates" / "letter.md").write_text("My wording")
    assert files.read_text(folder, "templates", "letter.md") == "My wording"
    custom_rules = folder / "custom" / "rules"
    custom_rules.mkdir()
    (custom_rules / "accounts.yaml").write_text(
        "_merge: true\naccounts:\n"
        "  - {id: '4200', name: Office rent}\n  - {id: '4980', name: Tools}\n"
    )
    merged = files.rules(folder, "accounts.yaml")
    assert merged == {
        "accounts": [
            {"id": "4930", "name": "Office"},
            {"id": "4200", "name": "Office rent"},
            {"id": "4980", "name": "Tools"},
        ],
        "rate": 19,
    }
    (custom_rules / "accounts.yaml").write_text("accounts: []\n")
    assert files.rules(folder, "accounts.yaml") == {"accounts": []}
    listing = {i["file"]: i for i in files.listing(folder)}
    assert listing["templates/letter.md"]["replaces"] and listing["rules/accounts.yaml"]["replaces"]
    with pytest.raises(ValueError):
        files.read_text(folder, "templates", "../../secret")


def test_check_finds_forbidden_imports_and_stray_custom_files(tmp_path):
    folder = write(
        tmp_path / "probe",
        basic("probe"),
        {
            "plugin.py": (
                "import httpx\nfrom docuhive.db import session\nfrom docuhive.sdk import Registry\n"
                "def setup(registry):\n    pass\n"
            ),
            "custom/templates/typo.md": "x",
        },
    )
    problems = check.check(folder)
    assert any("plugin.py:1: imports httpx" in p for p in problems)
    assert any("plugin.py:2: imports docuhive.db" in p for p in problems)
    assert not any("imports docuhive.sdk" in p for p in problems)
    assert any("custom/templates/typo.md: replaces nothing" in p for p in problems)
    (folder / "README.md").unlink()
    assert any(p.startswith("README.md") for p in check.check(folder))


def enabled(monkeypatch, granted: dict[str, list[str]]):
    rows = {k: SimpleNamespace(enabled=True, granted=v) for k, v in granted.items()}
    recorded: dict[str, dict] = {}
    monkeypatch.setattr(state, "states", lambda: rows)
    monkeypatch.setattr(state, "record", lambda pid, **kw: recorded.setdefault(pid, {}).update(kw))
    monkeypatch.setattr(state, "is_set", lambda pid, key: False)
    return recorded


SETUP_OK = """
from docuhive.sdk import Registry
from .helper import KIND

def setup(registry: Registry) -> None:
    @registry.notify_channel(KIND)
    def send(cfg, notification):
        pass

    @registry.setup_check
    def check(user):
        return None
"""


def test_loading_is_all_or_nothing_and_respects_approval(plugins_dir, monkeypatch):
    helper = {"plugin.py": SETUP_OK, "helper.py": "KIND = 'pigeon'\n"}
    write(plugins_dir / "good", basic("good"), helper)
    broken = SETUP_OK.replace("return None", "return None\n\n    raise RuntimeError('no luck')")
    write(plugins_dir / "broken", basic("broken"), {**helper, "plugin.py": broken})
    write(plugins_dir / "greedy", basic("greedy", "capabilities: [ai]\n"))
    write(plugins_dir / "needy", basic("needy", "depends_on: [greedy]\n"))
    write(
        plugins_dir / "configured",
        basic(
            "configured",
            "settings:\n  - {key: plate, type: string, label: Plate}\n"
            "setup_checks:\n"
            "  - {id: plate, title: Number plate, when_missing: plate, required: true}\n",
        ),
    )
    recorded = enabled(
        monkeypatch,
        {"good": [], "broken": [], "greedy": [], "needy": [], "configured": []},
    )
    runtime.start("api")
    assert set(runtime.LOADED) == {"good", "configured"}
    assert runtime.notify_channels().keys() == {"pigeon"}  # nothing from the broken plugin
    assert "no luck" in recorded["broken"]["error"]
    assert not any(k.startswith("docuhive_plugin_broken") for k in sys.modules)
    assert (
        "Needs your approval" in recorded["greedy"]["error"] and "ai" in recorded["greedy"]["error"]
    )
    assert "switched on" in recorded["needy"]["error"]
    checks = runtime.setup_checks(SimpleNamespace(id=1))
    assert [(c.id, c.status, c.required) for c in checks] == [
        ("plugin.configured.plate", "todo", True)
    ]
    assert checks[0].action_href == "/settings/plugins#configured"


def test_http_reaches_declared_hosts_only():
    patterns = ["api.example.org", "*.bank.test", "192.168.1.20"]
    assert http.allowed("api.example.org", patterns)
    assert http.allowed("online.bank.test", patterns)
    assert not http.allowed("evil.org", patterns)
    assert not http.allowed("bank.test.evil.org", patterns)
    assert http.allowed("192.168.1.20", patterns)
    assert not http.allowed("192.168.1.21", patterns)


def test_a_host_from_a_setting_must_name_a_declared_setting(tmp_path):
    from docuhive.api.plugins import _label

    good = basic(
        "importer",
        'capabilities: [network: ["setting:url"]]\n'
        "settings: [{ key: url, type: string, label: Paperless address }]\n",
    )
    manifest = load(write(tmp_path / "importer", good))
    assert manifest.hosts() == ["setting:url"]
    assert _label("network:setting:url", manifest) == (
        "Reach the address you enter in its settings (Paperless address)"
    )
    for wrong, problem in (
        ('capabilities: [network: ["setting:url"]]\n', "no setting with that key"),
        ('capabilities: [network: ["setting:URL!"]]\n', "names no setting"),
    ):
        with pytest.raises(ManifestError, match=problem):
            load(write(tmp_path / "bad" / "importer", basic("importer", wrong)))


def test_cli_add_update_new_keep_custom_files(plugins_dir, tmp_path, monkeypatch, capsys):
    source = write(tmp_path / "src" / "demo", basic("demo"), {"templates/a.md": "v1"})
    (source / "custom").mkdir()
    (source / "custom" / "author-only.txt").write_text("not for users")

    def run(*argv):
        args = SimpleNamespace(**dict(zip(argv[::2], argv[1::2], strict=True)))
        cli.run(args)

    run("plugins_action", "add", "path", str(source))
    installed = plugins_dir / "demo"
    assert not (installed / "custom" / "author-only.txt").exists()
    (installed / "custom" / "templates").mkdir(parents=True)
    (installed / "custom" / "templates" / "a.md").write_text("mine")
    with pytest.raises(SystemExit, match="already installed"):
        run("plugins_action", "add", "path", str(source))

    (source / "plugin.yaml").write_text(basic("demo").replace("0.1.0", "0.2.0"))
    (source / "templates" / "a.md").write_text("v2")
    run("plugins_action", "update", "id", "demo", "source", str(source), "force", False)
    assert (installed / "templates" / "a.md").read_text() == "v2"
    assert (installed / "custom" / "templates" / "a.md").read_text() == "mine"
    (source / "plugin.yaml").write_text(basic("demo"))
    with pytest.raises(SystemExit, match="older than"):
        run("plugins_action", "update", "id", "demo", "source", str(source), "force", False)

    run("plugins_action", "new", "id", "my-demo", "source", "demo")
    copy = load(plugins_dir / "my-demo")
    assert copy.id == "my-demo" and copy.version == "0.1.0"
    assert not (plugins_dir / "my-demo" / "custom" / "templates").exists()
    run("plugins_action", "new", "id", "fresh", "source", None)
    assert check.check(plugins_dir / "fresh") == []
    assert "Copied demo" in capsys.readouterr().out


def test_page_files_are_checked(tmp_path):
    from docuhive.plugins import pages

    folder = write(
        tmp_path / "probe",
        basic("probe"),
        {
            "pages/list.yaml": (
                "title: List\nnav: {label: L, icon: rocket}\nblocks:\n"
                "  - {type: table, source: rows, columns: [{field: a, label: A}]}\n"
                "  - {type: carousel}\n"
            ),
            "pages/_document.yaml": "title: X\nblocks:\n  - {type: text, text: hi}\n",
            "pages/_dashboard.yaml": (
                "title: D\nblocks:\n  - {type: text, text: a}\n  - {type: text, text: b}\n"
            ),
        },
    )
    found, problems = pages.load(folder)
    text = "\n".join(problems)
    assert "'rocket' is not an icon here" in text
    assert "is not a block type" in text
    assert "empty is required" in text  # every table says what to do when it is empty
    assert "say which documents it is for" in text
    assert "exactly one block" in text
    assert set(found) == {"_document", "_dashboard"}


def test_a_relative_plugins_folder_is_made_absolute(monkeypatch, tmp_path):
    from docuhive.config import reload
    from docuhive.plugins import discovery

    monkeypatch.chdir(tmp_path)
    (tmp_path / "plugins").mkdir()
    monkeypatch.setenv("DOCUHIVE_PLUGINS_DIR", "plugins")
    reload()
    assert discovery.plugins_dir() == (tmp_path / "plugins").resolve()


def test_two_plugins_may_extend_a_builtin_type_but_not_claim_the_same_new_one(monkeypatch):
    from docuhive import taxonomy
    from docuhive.plugins import install

    def adds(*ids):
        return taxonomy.Contribution.model_validate(
            {"document_types": [{"id": i, "label": i} for i in ids]}
        )

    monkeypatch.setattr(taxonomy, "CONTRIBUTIONS", [("bank", adds("invoice", "standing-order"))])
    taken = install._contributed_ids("steuer-de")
    assert "invoice" not in taken  # built in: both may add facts to it
    assert taken.get("standing-order") == "bank"

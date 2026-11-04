"""A green harness or an absent artifact must never sign off a release."""

import hashlib
import importlib.util
import json

import pytest
from qa_plugin import ROOT
from release import missing_evidence


def test_critical_coverage_gate_refuses_low_coverage_and_absent_vault(tmp_path, monkeypatch):
    import audit

    monkeypatch.setattr(audit, "ROOT", tmp_path)
    report = tmp_path / "tmp/qa/coverage.json"
    report.parent.mkdir(parents=True)
    data = {
        "files": {
            "services/docuhive/src/docuhive/" + module: {"summary": {"percent_covered": 95}}
            for module in audit.CRITICAL
        }
    }
    report.write_text(json.dumps(data))
    with pytest.raises(SystemExit, match="vault implementation absent"):
        audit.main()
    vault = tmp_path / "services/docuhive/src/docuhive/vault"
    vault.mkdir(parents=True)
    (vault / "write.py").write_text("def write(): pass\n")
    with pytest.raises(SystemExit, match="vault/write.py"):
        audit.main()
    data["files"]["services/docuhive/src/docuhive/vault/write.py"] = {
        "summary": {"percent_covered": 95}
    }
    report.write_text(json.dumps(data))
    audit.main()
    data["files"]["services/docuhive/src/docuhive/agents/validators.py"]["summary"][
        "percent_covered"
    ] = 94
    report.write_text(json.dumps(data))
    with pytest.raises(SystemExit, match="agents/validators.py"):
        audit.main()


def test_bundle_gate_refuses_missing_assets_maps_and_server_prompts(tmp_path, monkeypatch):
    import bundle

    monkeypatch.setattr(bundle, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="No production browser assets"):
        bundle.main()
    assets = tmp_path / "tmp/qa/web-static"
    assets.mkdir(parents=True)
    javascript = assets / "app.js"
    javascript.write_text("console.log('public browser code')")
    bundle.main()
    source_map = assets / "app.js.map"
    source_map.write_text("{}")
    with pytest.raises(SystemExit, match="source map"):
        bundle.main()
    source_map.unlink()
    prompt = (
        "A synthetic server-side prompt long enough to distinguish it from browser interface copy."
    )
    prompts = tmp_path / "config/defaults/prompts"
    prompts.mkdir(parents=True)
    (prompts / "classify.md").write_text(prompt)
    javascript.write_text(prompt)
    with pytest.raises(SystemExit, match="server configuration or prompt"):
        bundle.main()


@pytest.mark.req("QAR-TR-03")
def test_release_gate_requires_matching_candidate_and_real_signed_artifact(tmp_path):
    path = tmp_path / "tmp/qa/report.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"result":"passed"}')
    record = {
        "result": "passed",
        "runner": "QA",
        "date": "2026-11-04",
        "artifact": "tmp/qa/report.json",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    data = {"candidate": "candidate", "checks": {"privacy": record}}
    assert missing_evidence(data, {"privacy"}, "candidate", tmp_path) == []
    assert missing_evidence(data, {"privacy"}, "different", tmp_path) == ["privacy"]
    path.write_text("changed evidence")
    assert missing_evidence(data, {"privacy"}, "candidate", tmp_path) == ["privacy"]
    record["artifact"] = "../../outside.json"
    assert missing_evidence(data, {"privacy"}, "candidate", tmp_path) == ["privacy"]


def test_benchmark_percentile_does_not_interpolate_away_the_tail():
    spec = importlib.util.spec_from_file_location(
        "qa_search_bench", ROOT / "tests/perf/search_bench.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.percentile(list(range(1, 101)), 0.95) == 95
    with pytest.raises(ValueError):
        module.percentile([], 0.95)

"""A green harness or an absent artifact must never sign off a release."""

import hashlib
import importlib.util

import pytest
from qa_plugin import ROOT
from release import missing_evidence


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

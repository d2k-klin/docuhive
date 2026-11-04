"""Regression tests for QA's own generation, evidence and network enforcement."""

import importlib.util
import json
import socket
import zipfile
from trace import manual_entries, render, requirement_ids

import pytest
from fastapi.testclient import TestClient
from pytest_socket import SocketBlockedError
from qa_plugin import ROOT, fingerprint


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_evidence_fingerprint_tracks_source_but_ignores_generated_next_types(tmp_path):
    app = tmp_path / "apps/web"
    app.mkdir(parents=True)
    page = app / "page.tsx"
    page.write_text("original application source")
    generated = app / "next-env.d.ts"
    generated.write_text("generated dev type imports")
    before = fingerprint(tmp_path)
    generated.write_text("generated build type imports")
    assert fingerprint(tmp_path) == before
    page.write_text("changed application source")
    assert fingerprint(tmp_path) != before


@pytest.mark.req("QAR-TR-01", "QAR-TR-02", "QAR-TR-03")
def test_trace_gate_distinguishes_intent_from_evidence():
    assert requirement_ids("**STO-01**\n| NFR-10 Licensing | text |\nSTO-99 reference") == {
        "STO-01",
        "NFR-10",
    }
    tests = [{"nodeid": "test::case", "requirements": ["STO-01"], "pending": "QA-001"}]
    _, gaps = render({"STO-01", "NFR-10"}, tests, [], {})
    assert gaps == ["NFR-10", "STO-01"]
    _, gaps = render(
        {"STO-01"}, tests, [], {"test::case": {"outcome": "xfail", "at": "2026-11-04"}}
    )
    assert gaps == ["STO-01"]
    _, gaps = render(
        {"STO-01"}, tests, [], {"test::case": {"outcome": "passed", "at": "2026-11-04"}}
    )
    assert gaps == []
    manual = manual_entries(
        "| MC-01 | STO-01 | steps | expected | pending | pending | passed | pending |"
    )
    assert render({"STO-01"}, [], manual, {})[1] == ["STO-01"]
    manual[0].update(date="2026-11-04", environment="reference host", person="owner")
    assert render({"STO-01"}, [], manual, {})[1] == []
    manual[0]["date"] = "2026-99-99"
    assert render({"STO-01"}, [], manual, {})[1] == ["STO-01"]
    matrix, _ = render({"STO-01"}, tests, [], {"test::case": {"outcome": "failed"}})
    assert "| failed |" in matrix


@pytest.mark.req("QAR-TQ-01")
def test_default_suite_blocks_inet_sockets():
    with pytest.warns(UserWarning, match="socket.socket"), pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_corpus_same_seed_same_hashes_and_valid_formats(tmp_path):
    from PIL import Image

    generator = load_file("qa_corpus", "tests/corpus/generate.py")
    left = generator.generate(tmp_path / "left", cases=1)
    right = generator.generate(tmp_path / "right", cases=1)
    assert left == right
    doc = left["documents"][0]
    assert len(doc["files"]) == 10
    assert doc["facts"]["amount_total"]["value"] == "84.20"
    import yaml

    taxonomy = yaml.safe_load((ROOT / "config/defaults/taxonomy.yaml").read_text())
    invoice = next(t for t in taxonomy["document_types"] if t["id"] == doc["document_type"])
    assert set(doc["facts"]) <= {field["name"] for field in invoice["facts"]}
    assert Image.open(tmp_path / "left/case-001-phone.jpg").getexif()[274] == 6
    for kind in ("docx", "xlsx"):
        with zipfile.ZipFile(tmp_path / f"left/case-001.{kind}") as archive:
            assert archive.testzip() is None
            assert "[Content_Types].xml" in archive.namelist()


def test_fake_http_protocols_captures_and_unknown_requests():
    module = load_file("qa_mocks", "tests/mocks/server.py")
    with TestClient(module.create_app()) as client:
        payload = {
            "model": "qa-classify",
            "messages": [{"role": "user", "content": "QA-DOC:case-001"}],
            "tools": [{"type": "function", "function": {"name": "classification"}}],
        }
        result = client.post("/v1/chat/completions", json=payload)
        call = result.json()["choices"][0]["message"]["tool_calls"][0]
        assert json.loads(call["function"]["arguments"])["category"] == "utilities"
        assert client.get("/__calls").json()[0]["body"] == payload
        assert client.post("/v1/chat/completions", json={"model": "unknown"}).status_code == 400
        assert client.post("/v1/unknown", json={}).status_code == 404
        embedded = client.post(
            "/v1/embeddings", json={"model": "qa-embed", "input": ["first", "second"]}
        ).json()
        assert len(embedded["data"]) == 2 and len(embedded["data"][0]["embedding"]) == 1024
        response = client.post(
            "/v1/messages", json={"model": "qa-triage", "tools": [{"name": "triage"}]}
        ).json()
        assert response["content"][0]["input"]["archive"] is True
        assert client.delete("/mail/gmail/messages/m1").status_code == 405
        assert client.get("/mail/gmail/messages").json()["nextPageToken"] == "p2"


def test_openai_stream_has_completion_and_terminal_event():
    module = load_file("qa_stream_mocks", "tests/mocks/server.py")
    with TestClient(module.create_app()) as client:
        response = client.post("/v1/chat/completions", json={"model": "qa-chat", "stream": True})
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.text.endswith("data: [DONE]\n\n")
        assert '"finish_reason": "stop"' in response.text

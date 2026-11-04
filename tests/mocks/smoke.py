"""Real Strands + provider HTTP + real ai_runs; no monkeypatch or in-memory core."""

from docuhive.agents.base import run_structured
from docuhive.agents.triage import TriageOut
from docuhive.ai.embeddings import embedder


def main() -> None:
    variables = {
        key: "QA-DOC:case-001"
        for key in (
            "email_from",
            "subject",
            "received",
            "labels",
            "attachments",
            "snippet",
            "document_types",
        )
    }
    result = run_structured("triage", "triage", variables, TriageOut, restricted=False)
    assert result.value.archive is True
    assert result.value.attachments == ["case-001.pdf"]
    assert result.ai_run_id > 0
    engine = embedder()
    assert engine is not None
    vectors = engine.embed(["QA-DOC:case-001"])
    assert len(vectors) == 1 and len(vectors[0]) == 1024
    print("Real HTTP triage and embeddings passed; ai_runs recorded")


if __name__ == "__main__":
    main()

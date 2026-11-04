"""The spike report must preserve failed inputs and measure the actual processing result."""

import csv

import pytest
from docuhive.ingest import spike
from docuhive.ingest.errors import Quarantine


def test_report_retains_sources_and_records_expected_quarantine(tmp_path, monkeypatch):
    source, output = tmp_path / "input", tmp_path / "output"
    source.mkdir()
    (source / "encrypted.pdf").write_bytes(b"%PDF-1.4\nsynthetic")
    monkeypatch.setattr(
        spike, "isolated", lambda *args, **kwargs: (_ for _ in ()).throw(Quarantine("encrypted"))
    )
    rows = spike.run_spike(source, output)
    assert rows[0]["status"] == "quarantined" and rows[0]["error"] == "encrypted"
    assert (source / "encrypted.pdf").exists()
    assert (output / "sample-0001/encrypted.pdf").exists()
    with (output / "report.csv").open() as stream:
        assert next(csv.DictReader(stream))["error"] == "encrypted"
    assert "does not make" in (output / "report.md").read_text()
    with pytest.raises(ValueError, match="empty output"):
        spike.run_spike(source, output)


def test_successful_spike_records_text_pdfa_and_digital_preservation(tmp_path, monkeypatch):
    from docuhive.ingest.detect import Detected

    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"%PDF-1.4\nsynthetic")

    def execute(fn, *args, **kwargs):
        if fn is spike.detect:
            return Detected("application/pdf", "pdf", "pdf")
        if fn is spike.to_pdf:
            return source
        if fn is spike.page_count:
            return 2
        if fn is spike.extract_text:
            return "Synthetic text"
        if fn is spike.ocr:
            return True

    monkeypatch.setattr(spike, "isolated", execute)
    row = spike.process(source, tmp_path / "result")
    assert row["status"] == "ok"
    assert row["digital_text_preserved"] is True
    assert row["archive_pdfa"] is True
    assert row["text_chars_per_page"] == 7


def test_empty_sample_set_is_an_actionable_error(tmp_path):
    with pytest.raises(ValueError, match="no files"):
        spike.run_spike(tmp_path, tmp_path / "report")

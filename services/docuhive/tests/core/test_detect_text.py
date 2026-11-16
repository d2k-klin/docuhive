"""Windows-1252 text (many bank and older office exports) is accepted and read correctly."""

from docuhive.ingest.detect import detect, read_text


def test_windows_text_is_text(tmp_path):
    path = tmp_path / "export.csv"
    path.write_bytes("Buchung;Empfänger;Betrag\n03.03.2026;Müller;-84,20 €\n".encode("cp1252"))
    assert detect(path).kind == "text"
    assert "Müller" in read_text(path) and "€" in read_text(path)
    utf8 = tmp_path / "utf8.txt"
    utf8.write_text("Grüße", encoding="utf-8")
    assert read_text(utf8) == "Grüße"

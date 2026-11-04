"""A measurable OCR experiment; never inserts documents or chooses the production backend."""

import csv
import shutil
import time
from pathlib import Path

from docuhive.config.settings import get_settings

from .convert import to_pdf
from .detect import detect
from .errors import Quarantine
from .ocr import ocr
from .safety import isolated
from .text import extract_text, page_count
from .thumbs import thumbnail


def process(source: Path, directory: Path) -> dict:
    started = time.monotonic()
    result: dict = {
        "file": source.name,
        "mime": "",
        "pages": 0,
        "status": "failed",
        "error": "",
        "seconds": 0.0,
        "seconds_per_page": 0.0,
        "text_chars": 0,
        "text_chars_per_page": 0.0,
        "digital_text_preserved": "n/a",
        "archive_pdfa": False,
    }
    directory.mkdir(parents=True, exist_ok=False)
    local = directory / source.name
    shutil.copy2(source, local)
    try:
        detected = isolated(detect, local, timeout_s=30)
        result["mime"] = detected.mime
        pdf = isolated(to_pdf, local, detected, timeout_s=150)
        pages = isolated(page_count, pdf, timeout_s=30)
        result["pages"] = pages
        before = isolated(extract_text, pdf, timeout_s=60)
        archive = directory / "archive.pdf"
        result["archive_pdfa"] = isolated(
            ocr, pdf, archive, get_settings().ocr_languages, timeout_s=1800
        )
        content = isolated(extract_text, archive, timeout_s=60)
        isolated(thumbnail, archive, directory / "thumb.webp", timeout_s=60)
        (directory / "text.txt").write_text(content, encoding="utf-8")
        if before.strip() and detected.kind == "pdf":
            result["digital_text_preserved"] = " ".join(before.split()) == " ".join(content.split())
        result.update(
            status="ok",
            text_chars=len(content),
            text_chars_per_page=round(len(content) / max(pages, 1), 2),
        )
    except Quarantine as error:
        result.update(status="quarantined", error=str(error))
    except Exception as error:
        result.update(error=f"{type(error).__name__}: processing failed")
    result["seconds"] = round(time.monotonic() - started, 3)
    result["seconds_per_page"] = round(result["seconds"] / max(result["pages"], 1), 3)
    return result


def run_spike(input_dir: Path, output_dir: Path) -> list[dict]:
    if not input_dir.is_dir():
        raise ValueError("The sample directory does not exist")
    files = sorted(p for p in input_dir.iterdir() if p.is_file() and not p.name.startswith("."))
    if not files:
        raise ValueError("The sample directory contains no files")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Choose an empty output directory to preserve earlier reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        process(path, output_dir / f"sample-{index:04d}") for index, path in enumerate(files, 1)
    ]
    with (output_dir / "report.csv").open("w", newline="", encoding="utf-8") as report:
        writer = csv.DictWriter(report, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    columns = list(rows[0])

    def cell(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    lines = [
        "# OCR spike report",
        "",
        "Private report: do not commit real filenames or text.",
        "",
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    lines += ["| " + " | ".join(cell(row[column]) for column in columns) + " |" for row in rows]
    lines += ["", "This report does not make the GO/NO-GO decision. CER requires reference text."]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Processed {len(rows)} samples. Report: {output_dir / 'report.md'}")
    return rows

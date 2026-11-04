"""NFR-04 ingest time: submit synthetic scanned PDFs (image only, so every page needs OCR) and
time each until it is stored, through a real worker process.

    DOCUHIVE_DATABASE_URL=postgresql+psycopg://…/docuhive_test DOCUHIVE_VAULT_DIR=… \
      uv run python deploy/scripts/perf_ingest.py --pages 1 5 --rounds 3

Synthetic data only; refuses any database whose name does not end in `_test`.
"""

import argparse
import statistics
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.engine import make_url

LINES = [
    "Stadtwerke Muster GmbH",
    "Rechnung Nr. {n} vom 04.11.2026",
    "Stromlieferung Oktober 2026",
    "Verbrauch 312 kWh zu 0,32 EUR",
    "Grundgebühr 12,50 EUR",
    "Gesamtbetrag 112,34 EUR",
    "Fällig am 20.11.2026",
]


def scan(path, pages: int) -> None:
    """A4 at 300 dpi, black text on slightly grey paper, no text layer."""
    font = ImageFont.load_default(size=56)
    images = []
    for page in range(pages):
        image = Image.new("L", (2480, 3508), 245)
        draw = ImageDraw.Draw(image)
        for row in range(40):
            line = LINES[row % len(LINES)].format(n=f"{page}-{row}")
            draw.text((200, 250 + row * 76), line, fill=20, font=font)
        images.append(image)
    images[0].save(path, save_all=True, append_images=images[1:], resolution=300)


def run(owner: int, pages: int) -> float:
    from docuhive import db, ingest
    from docuhive.contracts import IngestRequest, SourceInfo, SourceKind
    from docuhive.db.models import Document

    path = ingest.incoming_dir() / f"perf-scan-{pages}p-{time.time_ns()}.pdf"
    scan(path, pages)
    started = time.perf_counter()
    result = ingest.submit(
        [path],
        IngestRequest(
            owner_id=owner, source=SourceInfo(kind=SourceKind.upload, original_filename=path.name)
        ),
    )
    while True:
        with db.session() as session:
            doc = session.get(Document, result.document_id)
            status = doc.status if doc else "missing"
        if status in {"stored", "quarantined"}:
            break
        if time.perf_counter() - started > 600:
            raise SystemExit(f"{pages} pages: still {status} after 600 s")
        time.sleep(0.2)
    if status != "stored":
        raise SystemExit(f"{pages} pages: quarantined ({doc.quarantine_reason})")
    return time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, nargs="+", default=[1, 5])
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    from docuhive.auth import create_user
    from docuhive.config.settings import get_settings

    if not (make_url(get_settings().database_url).database or "").endswith("_test"):
        raise SystemExit("Refusing: the database name must end in _test")
    owner = create_user(f"perf-{time.time_ns()}", "synthetic perf password 2026")
    worker = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from docuhive.cli import main; main()",
            "worker",
            "--queues",
            "ocr,default",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for pages in args.pages:
            seconds = sorted(run(owner, pages) for _ in range(args.rounds))
            print(
                {
                    "pages": pages,
                    "runs": len(seconds),
                    "median_s": round(statistics.median(seconds), 1),
                    "max_s": round(seconds[-1], 1),
                    "target_s": 60,
                    "ocr_languages": get_settings().ocr_languages,
                }
            )
    finally:
        worker.terminate()
        worker.wait(30)


if __name__ == "__main__":
    main()

"""Run DocuHive's real OCR on a synthetic scan; meant to run inside the worker image.

Unit tests mock ocrmypdf, so this is the check that the image's Tesseract, Ghostscript and
ocrmypdf actually work together. `make ocr-smoke` builds the image and pipes this file in.
"""

import sys
import tempfile
from pathlib import Path

import pikepdf
from docuhive.ingest.ocr import ocr
from docuhive.ingest.text import extract_text
from PIL import Image, ImageDraw, ImageFont

LINES = ["Stadtwerke Musterstadt", "Rechnung Nr. 4711", "Gesamtbetrag 123,45 EUR"]
EXPECTED = ["Rechnung", "4711", "123,45", "Gesamtbetrag"]


def main() -> int:
    work = Path(tempfile.mkdtemp())
    scan = Image.new("L", (2480, 3508), 255)  # A4 at 300 dpi
    draw = ImageDraw.Draw(scan)
    font = ImageFont.load_default(size=64)
    for i, line in enumerate(LINES):
        draw.text((200, 300 + i * 140), line, fill=0, font=font)
    scan = scan.rotate(1.5, fillcolor=255)  # slightly skewed, like a real scan
    pdf_in, pdf_out = work / "scan.pdf", work / "ocr.pdf"
    scan.save(pdf_in, resolution=300)

    pdfa = ocr(pdf_in, pdf_out, "deu+eng")
    with pikepdf.open(pdf_out) as pdf:
        part = pdf.open_metadata().get("pdfaid:part")
    text = extract_text(pdf_out)
    missing = [word for word in EXPECTED if word not in text]
    print(f"pdfa={pdfa} pdfaid:part={part} missing={missing}")
    if not pdfa or part != "2" or missing:
        print("OCR smoke failed. Text was:\n" + text, file=sys.stderr)
        return 1
    print("OCR smoke passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

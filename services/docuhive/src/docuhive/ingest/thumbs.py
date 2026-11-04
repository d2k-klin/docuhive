"""Render a bounded first-page preview."""

from contextlib import closing
from pathlib import Path

import pypdfium2 as pdfium

from .errors import Quarantine


def thumbnail(pdf: Path, out_webp: Path, width: int = 480) -> None:
    with pdfium.PdfDocument(pdf) as document:
        if not len(document):
            raise Quarantine("empty_pdf")
        with closing(document[0]) as page:
            page_width, page_height = page.get_size()
            scale = min(width / max(page_width, 1), width * 4 / max(page_height, 1))
            bitmap = page.render(scale=scale)
            try:
                bitmap.to_pil().convert("RGB").save(out_webp, format="WEBP", quality=80)
            finally:
                bitmap.close()

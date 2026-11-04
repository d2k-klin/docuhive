"""Extract page text without invoking another OCR pass."""

import re
from contextlib import closing
from pathlib import Path

import pypdfium2 as pdfium

from .errors import Quarantine
from .safety import MAX_PAGES


def extract_text(pdf: Path) -> str:
    with pdfium.PdfDocument(pdf) as document:
        if len(document) > MAX_PAGES:
            raise Quarantine("too_many_pages")
        pages = []
        for index in range(len(document)):
            with closing(document[index]) as page, closing(page.get_textpage()) as textpage:
                value = textpage.get_text_range().replace("\r\n", "\n").replace("\r", "\n")
                pages.append(re.sub(r"[^\S\n]+", " ", value).strip())
        return "\f".join(pages)


def page_count(pdf: Path) -> int:
    with pdfium.PdfDocument(pdf) as document:
        return len(document)

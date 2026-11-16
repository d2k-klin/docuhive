"""Content detection without trusting a filename or decoding arbitrary binary as text."""

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import filetype

from .errors import Quarantine


@dataclass(frozen=True)
class Detected:
    mime: str
    ext: str
    kind: str


OFFICE = {
    "word/document.xml": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ),
    "xl/workbook.xml": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    "ppt/presentation.xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "pptx",
    ),
}
ODF = {
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
}
IMAGES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/tiff": "tiff",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
}


def detect(path: Path) -> Detected:
    with path.open("rb") as stream:
        head = stream.read(8192)
    if not head:
        raise Quarantine("empty_file")
    if head.startswith(b"%PDF-"):
        return Detected("application/pdf", "pdf", "pdf")
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                # Never inflate office archives during detection. Bound advertised expansion.
                if (
                    len(entries) > 10000
                    or sum(e.file_size for e in entries) > 500_000_000
                    or any(e.file_size > max(1, e.compress_size) * 1000 for e in entries)
                ):
                    raise Quarantine("archive_expansion_limit")
                names = set(archive.namelist())
                if "[Content_Types].xml" in names:
                    for marker, (mime, extension) in OFFICE.items():
                        if marker in names:
                            return Detected(mime, extension, "office")
                if "mimetype" in names:
                    entry = archive.getinfo("mimetype")
                    if entry.file_size <= 256:
                        mime = archive.read(entry).decode("ascii", errors="replace").strip()
                        if mime in ODF:
                            return Detected(mime, ODF[mime], "office")
        except zipfile.BadZipFile as error:
            raise Quarantine("invalid_archive") from error
        raise Quarantine("unsupported_type:application/zip")
    guess = filetype.guess(head)
    if guess and guess.mime in IMAGES:
        return Detected(guess.mime, IMAGES[guess.mime], "image")
    if guess:
        raise Quarantine(f"unsupported_type:{guess.mime}")
    try:
        # Validate the entire file incrementally, including multibyte boundaries.
        with path.open(encoding="utf-8-sig") as stream:
            while chunk := stream.read(65536):
                if "\x00" in chunk:
                    raise Quarantine("unsupported_type:binary")
    except UnicodeError:
        # Older Windows software (many bank exports) writes Windows-1252 text.
        if not _windows_text(path):
            raise Quarantine("unsupported_type:binary") from None
    prefix = read_text(path)[:8192]
    if re.search(r"(?im)^(?:from|received|mime-version):", prefix):
        return Detected("message/rfc822", "eml", "email")
    if re.search(r"(?i)<!doctype\s+html|<html\b", prefix[:1024]):
        return Detected("text/html", "html", "html")
    return Detected("text/plain", "txt", "text")


def _windows_text(path: Path) -> bool:
    data = path.read_bytes()
    # UTF-16 and UTF-32 text (byte-order marks) is not supported; NUL bytes mean binary.
    if b"\x00" in data or data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return False
    try:
        text = data.decode("cp1252")
    except UnicodeDecodeError:
        return False
    controls = sum(1 for c in text if ord(c) < 32 and c not in "\t\r\n\f")
    return controls <= len(text) // 1000


def read_text(path: Path) -> str:
    """A text file as UTF-8, or as Windows-1252 when it is not valid UTF-8."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")

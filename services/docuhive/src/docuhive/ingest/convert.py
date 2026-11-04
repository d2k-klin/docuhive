"""Pure conversion steps reused by the OCR feasibility spike."""

import warnings
from html import escape
from pathlib import Path

import httpx
import img2pdf
import pikepdf
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from docuhive.config.settings import get_settings

from .detect import Detected
from .errors import Quarantine, Transient
from .html import html_document, render_email, sanitize
from .safety import MAX_IMAGE_PIXELS, MAX_PAGES

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
register_heif_opener()


def to_pdf(path: Path, detected: Detected) -> Path:
    output = path.with_name(path.name + ".converted.pdf")
    if detected.kind == "pdf":
        try:
            with pikepdf.open(path, password="") as pdf:
                if len(pdf.pages) > MAX_PAGES:
                    raise Quarantine("too_many_pages")
                pdf.save(output)
        except pikepdf.PasswordError as error:
            raise Quarantine("encrypted") from error
    elif detected.kind == "image":
        frames: list[str] = []
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    count = getattr(image, "n_frames", 1)
                    if count > MAX_PAGES:
                        raise Quarantine("too_many_pages")
                    for index in range(count):
                        image.seek(index)
                        frame = ImageOps.exif_transpose(image).convert("RGB")
                        target = path.with_name(f"{path.name}.frame-{index}.jpg")
                        frame.save(target, quality=95, dpi=(300, 300))
                        frames.append(str(target))
            output.write_bytes(img2pdf.convert(frames))
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise Quarantine("image_too_large") from error
        finally:
            for frame_path in frames:
                Path(frame_path).unlink(missing_ok=True)
    elif detected.kind in {"office", "html", "email", "text"}:
        if detected.kind == "office":
            endpoint, filename, data = (
                "libreoffice/convert",
                f"input.{detected.ext}",
                path.read_bytes(),
            )
        else:
            endpoint, filename = "chromium/convert/html", "index.html"
            if detected.kind == "email":
                rendered = render_email(path)
            elif detected.kind == "html":
                rendered = html_document(sanitize(path.read_text(encoding="utf-8-sig")))
            else:
                rendered = html_document(
                    f"<pre>{escape(path.read_text(encoding='utf-8-sig'))}</pre>"
                )
            data = rendered.encode()
        with httpx.Client(timeout=120, follow_redirects=False, trust_env=False) as client:
            try:
                response = client.post(
                    f"{get_settings().gotenberg_url}/forms/{endpoint}",
                    files={"files": (filename, data)},
                )
                response.raise_for_status()
            except httpx.TimeoutException as error:
                # Could be the service or the document: retried a few times, then quarantined.
                raise TimeoutError("converter_timeout") from error
            except httpx.ConnectError as error:
                raise Transient("converter_unavailable") from error
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 429 or error.response.status_code >= 500:
                    raise Transient(f"converter_http_{error.response.status_code}") from error
                raise Quarantine(f"conversion_http_{error.response.status_code}") from error
            output.write_bytes(response.content)
    else:
        raise Quarantine(f"unsupported_type:{detected.mime}")
    with pikepdf.open(output) as pdf:
        if len(pdf.pages) > MAX_PAGES:
            output.unlink(missing_ok=True)
            raise Quarantine("too_many_pages")
    return output


def combine(pdfs: list[Path], output: Path) -> Path:
    """Several photographed pages, in order, as one PDF."""
    with pikepdf.new() as merged:
        sources = [pikepdf.open(path) for path in pdfs]
        try:
            for source in sources:
                merged.pages.extend(source.pages)
            if len(merged.pages) > MAX_PAGES:
                raise Quarantine("too_many_pages")
            merged.save(output)
        finally:
            for source in sources:
                source.close()
    return output

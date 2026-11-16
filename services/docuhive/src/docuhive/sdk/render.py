"""Text and PDFs from a plugin's templates (`templates/`, `custom/templates/` first).

Templates are Jinja2 in a sandbox: they can format the values they are given and nothing else.
PDFs are printed from HTML by the converter already in the stack (Chromium in Gotenberg), with
no network: files next to the template in `templates/assets/` are sent along, everything else
is refused. Letters extend the core's `_letter.html`, which fits a window envelope.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from jinja2 import ChoiceLoader, FunctionLoader, StrictUndefined
from jinja2.sandbox import ImmutableSandboxedEnvironment

from ._plugin import current
from .pages import ActionError

CORE = Path(__file__).parent / "templates"
# Chromium honours this inside the page, on top of the converter's own deny list.
NO_NETWORK = (
    '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
    "img-src data: file:; style-src 'unsafe-inline' file:; font-src data: file:\">"
)


class RenderError(ActionError):
    """The PDF could not be made; the message is shown on the page."""


def _environment(html: bool) -> ImmutableSandboxedEnvironment:
    registry = current()

    def plugin_template(name: str) -> str | None:
        try:
            return registry.template(name)
        except FileNotFoundError:
            return None

    def core_template(name: str) -> str | None:
        path = CORE / name
        return path.read_text(encoding="utf-8") if name.startswith("_") and path.is_file() else None

    return ImmutableSandboxedEnvironment(
        loader=ChoiceLoader([FunctionLoader(plugin_template), FunctionLoader(core_template)]),
        autoescape=html,
        undefined=StrictUndefined,  # a missing value is an error, not an empty line on a letter
    )


def text(template: str, context: dict[str, Any]) -> str:
    """A template filled in: a mail body, a letter's text. HTML templates are escaped."""
    return _environment(template.endswith(".html")).get_template(template).render(**context)


def pdf(template: str, context: dict[str, Any], *, pdfa: bool = False) -> bytes:
    """An HTML template printed to PDF. `pdfa=True` makes PDF/A-3b, which can carry an
    e-invoice (see `attach`)."""
    from docuhive.config import get_settings

    if not template.endswith(".html"):
        raise RenderError("PDFs are printed from .html templates")
    page = text(template, context)
    page = (
        page.replace("<head>", f"<head>{NO_NETWORK}", 1) if "<head>" in page else NO_NETWORK + page
    )
    files: list[tuple[str, tuple[str, bytes]]] = [("files", ("index.html", page.encode()))]
    assets = current().path / "templates" / "assets"
    custom = current().path / "custom" / "templates" / "assets"
    for folder in (assets, custom):  # custom/ last: its files replace the plugin's
        if folder.is_dir():
            files += [
                ("files", (p.name, p.read_bytes())) for p in sorted(folder.iterdir()) if p.is_file()
            ]
    # A4 with no margins unless the template's @page says otherwise (Chromium prints Letter).
    data = {
        "paperWidth": "8.27",
        "paperHeight": "11.69",
        "marginTop": "0",
        "marginBottom": "0",
        "marginLeft": "0",
        "marginRight": "0",
        "preferCssPageSize": "true",
        "printBackground": "true",
    }
    if pdfa:
        data["pdfa"] = "PDF/A-3b"
    try:
        with httpx.Client(timeout=120, follow_redirects=False, trust_env=False) as client:
            response = client.post(
                f"{get_settings().gotenberg_url}/forms/chromium/convert/html",
                files=files,
                data=data,
            )
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise RenderError("The PDF could not be made: the converter is not reachable.") from error
    return response.content


def attach(pdf_bytes: bytes, name: str, data: bytes, *, relationship: str = "Alternative") -> bytes:
    """Embed a file in a PDF, as ZUGFeRD / Factur-X do with the invoice XML."""
    import io

    import pikepdf

    with pikepdf.open(io.BytesIO(pdf_bytes)) as document:
        stamp = datetime.now(UTC).strftime("D:%Y%m%d%H%M%SZ")
        spec = pikepdf.AttachedFileSpec(
            document,
            data,
            description=name,
            filename=name,
            mime_type="text/xml" if name.endswith(".xml") else "application/octet-stream",
            creation_date=stamp,
            mod_date=stamp,
        )
        spec.obj.AFRelationship = pikepdf.Name(f"/{relationship}")
        document.attachments[name] = spec
        files = document.Root.get("/AF", pikepdf.Array())
        files.append(spec.obj)
        document.Root.AF = files
        out = io.BytesIO()
        document.save(out)
    return out.getvalue()

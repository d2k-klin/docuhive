"""Self-contained email rendering with a deliberately small inert HTML allowlist."""

import base64
from email import policy
from email.parser import BytesParser
from html import escape
from html.parser import HTMLParser
from pathlib import Path

ALLOWED = {
    "p",
    "br",
    "div",
    "span",
    "b",
    "strong",
    "i",
    "em",
    "table",
    "thead",
    "tbody",
    "tr",
    "td",
    "th",
    "h1",
    "h2",
    "h3",
    "h4",
    "ul",
    "ol",
    "li",
    "pre",
    "blockquote",
}
BLOCKED = {"script", "style", "iframe", "object", "embed", "svg", "math", "template"}


class Sanitizer(HTMLParser):
    def __init__(self, images: dict[str, str]):
        super().__init__(convert_charrefs=True)
        self.images = images
        self.output: list[str] = []
        self.blocked = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in BLOCKED:
            self.blocked += 1
        if self.blocked:
            return
        if tag in ALLOWED:
            self.output.append(f"<{tag}>")
        elif tag == "img":
            source = dict(attrs).get("src") or ""
            if source.startswith("cid:") and source[4:] in self.images:
                self.output.append(f'<img src="{self.images[source[4:]]}" alt="Inline image">')

    def handle_endtag(self, tag: str) -> None:
        if tag in BLOCKED:
            self.blocked = max(0, self.blocked - 1)
            return
        if not self.blocked and tag in ALLOWED and tag != "br":
            self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.blocked:
            self.output.append(escape(data))


def sanitize(body: str, images: dict[str, str] | None = None) -> str:
    parser = Sanitizer(images or {})
    parser.feed(body)
    return "".join(parser.output)


def html_document(body: str) -> str:
    return (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>' + body + "</body></html>"
    )


def render_email(path: Path) -> str:
    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    headers = (
        "<dl>"
        + "".join(
            f"<dt>{key}</dt><dd>{escape(str(message.get(key, '')))}</dd>"
            for key in ("From", "To", "Date", "Subject")
        )
        + "</dl>"
    )
    images: dict[str, str] = {}
    for part in message.walk():
        cid, mime = part.get("Content-ID"), part.get_content_type()
        if cid and mime in {"image/png", "image/jpeg", "image/webp"}:
            data = part.get_payload(decode=True) or b""
            if isinstance(data, bytes) and len(data) <= 10_000_000:
                images[str(cid).strip("<>")] = (
                    f"data:{mime};base64,{base64.b64encode(data).decode()}"
                )
    body = message.get_body(preferencelist=("html", "plain"))
    content = str(body.get_content()) if body else ""
    rendered = (
        sanitize(content, images)
        if body and body.get_content_type() == "text/html"
        else (f"<pre>{escape(content)}</pre>")
    )
    return html_document(headers + rendered)

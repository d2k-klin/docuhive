"""Generate 150 deterministic synthetic files with the installed OCR libraries and stdlib."""

import argparse
import hashlib
import io
import json
import random
import zipfile
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path
from xml.sax.saxutils import escape

import pikepdf
import yaml
from PIL import Image, ImageDraw, ImageFont


def pdf_bytes(text: str) -> bytes:
    with pikepdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(612, 792))
        font = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica
            )
        )
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
        lines = [
            line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            for line in text.splitlines()
        ]
        body = "BT /F1 14 Tf 50 740 Td 22 TL " + " T* ".join(f"({s}) Tj" for s in lines) + " ET"
        page.Contents = pdf.make_stream(body.encode("ascii"))
        output = io.BytesIO()
        pdf.save(output, deterministic_id=True)
        return output.getvalue()


def office_bytes(kind: str, text: str) -> bytes:
    output = io.BytesIO()
    word = kind == "docx"
    part = "word/document.xml" if word else "xl/workbook.xml"
    content_type = "wordprocessingml.document" if word else "spreadsheetml.sheet"
    files = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/{part}" ContentType="application/vnd.openxmlformats-officedocument.'
        f'{content_type}.main+xml"/>'
        + (
            ""
            if word
            else '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        + "</Types>",
        "_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        f'officeDocument" Target="{part}"/></Relationships>',
    }
    if word:
        files[part] = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        )
        files[part] += (
            "<w:body>"
            + "".join(f"<w:p><w:r><w:t>{escape(s)}</w:t></w:r></w:p>" for s in text.splitlines())
            + "</w:body></w:document>"
        )
    else:
        files[part] = '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        files[part] += (
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        )
        files[part] += '<sheets><sheet name="Invoice" sheetId="1" r:id="rId1"/></sheets></workbook>'
        files["xl/_rels/workbook.xml.rels"] = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        )
        files["xl/_rels/workbook.xml.rels"] += (
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>'
        )
        files["xl/worksheets/sheet1.xml"] = (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        )
        files["xl/worksheets/sheet1.xml"] += (
            "".join(
                f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>{escape(s)}</t></is></c></row>'
                for i, s in enumerate(text.splitlines(), 1)
            )
            + "</sheetData></worksheet>"
        )
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(zipfile.ZipInfo(name, (2025, 1, 1, 0, 0, 0)), content.encode())
    return output.getvalue()


def generate(root: Path, seed: int = 42, cases: int = 15) -> dict:
    import pillow_heif

    pillow_heif.register_heif_opener()
    root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    manifest = {"schema": 1, "seed": seed, "synthetic": True, "documents": []}
    categories = [
        "utilities",
        "finance",
        "employment",
        "housing",
        "insurance",
        "government",
        "purchases",
    ]
    for index in range(1, cases + 1):
        marker = f"QA-DOC:case-{index:03}"
        cents = 8420 if index == 1 else rng.randint(100, 50000)
        amount = f"{cents // 100}.{cents % 100:02}"
        restricted = index >= 12
        category = "health" if restricted else categories[(index - 1) % len(categories)]
        if index == 13:
            category = "personal"
        if index == 14:
            category = "government/identity"
        language = "de" if index % 2 else "en"
        title = "Rechnung" if language == "de" else "Invoice"
        text = (
            f"{marker}\n{title} QA-{index:03}\nQA Utility {index:02}\n"
            f"2025-11-01\nAmount: {amount} EUR\n"
        )
        stem = f"case-{index:03}"
        pdf = pdf_bytes(text)
        (root / f"{stem}.pdf").write_bytes(pdf)
        (root / f"{stem}.txt").write_text(text)
        (root / f"{stem}.html").write_text(
            f"<!doctype html><html><body><pre>{escape(text)}</pre></body></html>"
        )
        for kind in ("docx", "xlsx"):
            (root / f"{stem}.{kind}").write_bytes(office_bytes(kind, text))
        image = Image.new("RGB", (1200, 1600), "white")
        draw = ImageDraw.Draw(image)
        draw.multiline_text(
            (80, 140), text, fill="black", font=ImageFont.load_default(size=32), spacing=16
        )
        image.rotate(rng.uniform(-3, 3), fillcolor="white").save(root / f"{stem}-scan.png")
        image.rotate(90, expand=True).save(root / f"{stem}-rotated.png")
        exif = Image.Exif()
        exif[274] = 6
        image.rotate(90, expand=True).save(root / f"{stem}-phone.jpg", exif=exif, quality=85)
        image.save(root / f"{stem}.heic", quality=70)
        mail = EmailMessage(policy=SMTP)
        mail["From"], mail["To"] = "sender@example.invalid", "archive@example.invalid"
        mail["Subject"] = f"Synthetic {marker}"
        mail["Date"] = "Sat, 01 Nov 2025 08:00:00 +0000"
        mail["Message-ID"] = f"<{stem}@example.invalid>"
        mail.set_content(text)
        mail.add_attachment(pdf, maintype="application", subtype="pdf", filename=f"{stem}.pdf")
        mail.set_boundary(f"qa-{seed}-{index}")
        (root / f"{stem}.eml").write_bytes(mail.as_bytes())
        files = sorted(root.glob(f"{stem}.*")) + sorted(root.glob(f"{stem}-*"))
        manifest["documents"].append(
            {
                "id": stem,
                "marker": marker,
                "owner": "bob" if index >= 14 else "alice",
                "shared": False,
                "category": category,
                "document_type": "invoice",
                "correspondent": f"QA Utility {index:02}",
                "document_date": "2025-11-01",
                "language": language,
                "restricted": restricted,
                "tags": ["private"] if index == 13 else [],
                "facts": {"amount_total": {"type": "money", "value": amount, "currency": "EUR"}},
                "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            }
        )
    (root / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=True))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("tmp/qa/corpus"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(
        json.dumps(
            {"documents": len(generate(args.out, args.seed)["documents"]), "out": str(args.out)}
        )
    )

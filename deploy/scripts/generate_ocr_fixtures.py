"""Generate a small public, synthetic corpus for smoke checks; it cannot pass the real OCR gate."""

import argparse
from pathlib import Path

import pikepdf
from PIL import Image, ImageDraw, ImageFont


def generate(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with pikepdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(612, 792))
        font = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica
            )
        )
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
        page.Contents = pdf.make_stream(
            b"BT /F1 14 Tf 72 700 Td (Synthetic invoice 84.20 EUR) Tj ET"
        )
        pdf.save(root / "digital.pdf")
        pdf.save(
            root / "encrypted.pdf",
            encryption=pikepdf.Encryption(owner="synthetic-owner", user="synthetic"),
        )
    image = Image.new("RGB", (1600, 2200), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    draw.multiline_text(
        (140, 200),
        "Synthetic invoice\nAmount: 84.20 EUR\nDate: 2026-11-03",
        fill="black",
        font=font,
        spacing=30,
    )
    image.save(root / "scan.png", dpi=(300, 300))
    (root / "receipt.txt").write_text("Synthetic receipt\nAmount: 84.20 EUR\n", encoding="utf-8")
    (root / "receipt.html").write_text(
        "<!doctype html><html><body><h1>Synthetic receipt</h1><p>84.20 EUR</p></body></html>"
    )
    (root / "receipt.eml").write_text(
        "From: sender@example.invalid\nTo: archive@example.invalid\nSubject: Synthetic receipt\n"
        "MIME-Version: 1.0\nContent-Type: text/plain; charset=utf-8\n\nAmount: 84.20 EUR\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    generate(parser.parse_args().out)

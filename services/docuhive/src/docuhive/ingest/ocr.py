"""OCR policy and limited fallbacks, executed in an isolated process by the spike."""

from pathlib import Path
from typing import Any

import ocrmypdf
from ocrmypdf.exceptions import EncryptedPdfError, ExitCode, PriorOcrFoundError

from docuhive.config.settings import get_settings

from .errors import Quarantine


def ocr(pdf_in: Path, pdf_out: Path, languages: str) -> bool:
    options: dict[str, Any] = dict(
        output_type="pdfa-2",
        skip_text=True,
        rotate_pages=True,
        deskew=True,
        clean=False,
        language=languages.split("+"),
        jobs=get_settings().ocr_jobs,
        optimize=1,
        tesseract_timeout=180,
        progress_bar=False,
    )
    for _attempt in range(3):
        try:
            result = ocrmypdf.ocr(pdf_in, pdf_out, **options)
            if result == ExitCode.pdfa_conversion_failed:
                options["output_type"] = "pdf"
            elif result not in (None, ExitCode.ok):
                raise Quarantine(f"ocr_exit:{result}")
            else:
                return options["output_type"] == "pdfa-2"
        except EncryptedPdfError as error:
            raise Quarantine("encrypted") from error
        except PriorOcrFoundError:
            options.update(force_ocr=False, skip_text=True)
        except Exception as error:
            if "deskew" not in str(error).lower() or not options["deskew"]:
                raise
            options["deskew"] = False
        pdf_out.unlink(missing_ok=True)
    raise Quarantine("ocr_fallbacks_exhausted")

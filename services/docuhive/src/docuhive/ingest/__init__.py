"""Ingest contract; production backend is selected after the OCR gate."""

from pathlib import Path

from docuhive.contracts import IngestRequest, IngestResult


class IngestRejected(Exception):
    pass


class UnsupportedType(IngestRejected):
    pass


class TooLarge(IngestRejected):
    pass


def incoming_dir() -> Path:
    raise NotImplementedError("OA-M3: pending the OA-M1 OCR gate")


def submit(files: list[Path], req: IngestRequest) -> IngestResult:
    raise NotImplementedError("OA-M3: pending the OA-M1 OCR gate")

"""Bounded multipart intake for browser capture and scoped personal tokens."""

import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.datastructures import UploadFile
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from docuhive import documents, ingest
from docuhive.auth import scope
from docuhive.config.settings import get_settings
from docuhive.contracts import (
    CurrentUser,
    IngestRequest,
    IngestResult,
    MetadataPatch,
    SourceInfo,
    SourceKind,
)

from .documents import validate

router = APIRouter(tags=["documents"])


class UploadLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        total = 0

        async def bounded_receive() -> Message:
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            # Bound multipart framing as well as files, including chunked requests.
            if total > get_settings().max_upload_mb * 1024 * 1024 + 1024 * 1024:
                raise ingest.TooLarge()
            return message

        limited = scope["type"] == "http" and scope["path"] == "/api/upload"
        await self.app(scope, bounded_receive if limited else receive, send)


@router.post(
    "/api/upload",
    response_model=IngestResult,
    status_code=202,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["files"],
                        "properties": {
                            "files": {
                                "type": "array",
                                "maxItems": 50,
                                "items": {"type": "string", "format": "binary"},
                            }
                        },
                    }
                }
            },
        }
    },
)
async def upload(
    request: Request,
    user: Annotated[CurrentUser, Depends(scope("upload"))],
    combine: bool = False,
    source: Literal["upload", "mobile", "api"] = "upload",
    shared: bool = True,
    expected_owner_id: int | None = None,
    category: str | None = None,
    tags: Annotated[list[str], Query()] = [],  # noqa: B006
) -> IngestResult:
    # Set at upload time, these are the user's choices and locked against the AI (DOC-08).
    patch = MetadataPatch(category=category or None, tags_add=[t for t in tags if t.strip()])
    validate(patch)
    if expected_owner_id is not None and expected_owner_id != user.id:
        raise HTTPException(403, "Sign in to the account that saved this capture.")
    paths: list[Path] = []
    try:
        async with request.form(max_files=50, max_fields=4) as form:
            files = form.getlist("files")
            if not files or any(not isinstance(f, UploadFile) for f in files):
                raise HTTPException(422, "Choose at least one file to upload.")
            incoming = ingest.incoming_dir()
            total = 0
            for file in files:
                assert isinstance(file, UploadFile)
                # Keep only the suffix; filenames must never control server paths.
                suffix = Path(file.filename or "upload").suffix[:16]
                with tempfile.NamedTemporaryFile(dir=incoming, suffix=suffix, delete=False) as out:
                    paths.append(Path(out.name))
                    while block := await file.read(1024 * 1024):
                        total += len(block)
                        if total > get_settings().max_upload_mb * 1024 * 1024:
                            raise ingest.TooLarge()
                        out.write(block)
                    out.flush()
                    os.fsync(out.fileno())
            kind = SourceKind.api if request.state.token_scopes is not None else SourceKind(source)
            first = files[0]
            assert isinstance(first, UploadFile)
            req = IngestRequest(
                owner_id=user.id,
                source=SourceInfo(
                    kind=kind,
                    original_filename=(first.filename or "upload")
                    .replace("\\", "/")
                    .rsplit("/", 1)[-1],
                ),
                combine=combine,
                shared=shared,
            )
            # Conversion, validation, dedupe and analysis belong to the shared pipeline.
            from starlette.concurrency import run_in_threadpool

            result = await run_in_threadpool(ingest.submit, paths, req)
    except ingest.TooLarge:
        raise HTTPException(
            413, {"code": "too_large", "message": "Choose smaller files.", "details": {}}
        ) from None
    except ingest.IngestRejected:
        raise HTTPException(
            415,
            {"code": "unsupported_type", "message": "Choose a supported file type.", "details": {}},
        ) from None
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
    if result.status == "staged" and (patch.category or patch.tags_add):
        documents.apply_metadata(result.document_id, patch, actor=f"user:{user.id}")
    return result

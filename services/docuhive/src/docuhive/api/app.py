"""FastAPI factory with fail-fast settings and optional intelligence startup."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from docuhive import __version__
from docuhive.config.settings import get_settings
from docuhive.startup import start_intelligence, start_plugins

from .routers import ROUTERS


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    import threading

    from docuhive.plugins import runtime

    get_settings()
    start_plugins("api")
    start_intelligence()
    stopped = threading.Event()
    runtime.watch("api", stopped)  # plugins switched on elsewhere start here within seconds
    yield
    stopped.set()


def create_app() -> FastAPI:
    get_settings()
    app = FastAPI(title="DocuHive", version=__version__, lifespan=lifespan)
    from .upload import UploadLimitMiddleware

    app.add_middleware(UploadLimitMiddleware)
    for router in ROUTERS:
        app.include_router(router)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        detail = error.detail
        body = (
            detail
            if isinstance(detail, dict) and "code" in detail
            else {
                "code": f"http_{error.status_code}",
                "message": str(detail),
                "details": {},
            }
        )
        return JSONResponse({"error": body}, status_code=error.status_code, headers=error.headers)

    from docuhive.documents.holds import Held

    @app.exception_handler(Held)
    async def held(request: Request, error: Held) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "document_held",
                    "message": str(error),
                    "details": {
                        "fields": error.fields,
                        "until": error.until.isoformat() if error.until else None,
                    },
                }
            },
            status_code=409,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Check the supplied fields and try again.",
                    "details": {
                        "fields": [".".join(str(x) for x in e["loc"]) for e in error.errors()]
                    },
                }
            },
            status_code=422,
        )

    return app

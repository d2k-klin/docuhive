"""FastAPI factory with fail-fast settings and optional intelligence startup."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from docuhive import __version__
from docuhive.config.settings import get_settings
from docuhive.startup import start_intelligence

from .routers import ROUTERS


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings()
    start_intelligence()
    yield


def create_app() -> FastAPI:
    get_settings()
    app = FastAPI(title="DocuHive", version=__version__, lifespan=lifespan)
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

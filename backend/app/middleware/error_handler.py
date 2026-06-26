import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.errors import (
    ConfigurationError,
    DlpViolationError,
    GenerationError,
    SessionNotFoundError,
    SlideForgeError,
    StorageError,
)

logger = structlog.get_logger(__name__)

_STATUS_MAP: dict[type[SlideForgeError], int] = {
    ConfigurationError: 500,
    DlpViolationError: 400,
    SessionNotFoundError: 404,
    GenerationError: 502,
    StorageError: 500,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(SlideForgeError)
    async def _slideforge_error_handler(request: Request, exc: SlideForgeError) -> JSONResponse:
        status = 500
        for exc_type, code in _STATUS_MAP.items():
            if isinstance(exc, exc_type):
                status = code
                break
        logger.warning("SlideForgeError", error_code=exc.code, message=exc.message, path=request.url.path, method=request.method)
        return JSONResponse(
            status_code=status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def _generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", path=request.url.path, method=request.method, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}},
        )

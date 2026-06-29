import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings, validate_settings
from app.middleware.error_handler import register_error_handlers
from app.middleware.rate_limit import register_rate_limiter
from app.routers import decks, generate, health, onlyoffice, refine, export, preview, uploads, v2
from app.services.platform.storage import StorageService
from app.services.platform.uploads import UploadService


def _validate_config() -> None:
    validate_settings(settings)


def _configure_logging() -> None:
    if settings.log_format == "json":
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.StackFormatterRenderer(),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            logger_factory=structlog.PrintLoggerFactory(),
        )
    else:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.dev.ConsoleRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    _validate_config()
    from app.dependencies import (
        close_deck_file_storage,
        get_database,
        get_deck_file_storage,
        get_deck_repository,
        get_deck_version_service,
        get_onlyoffice_service,
        get_deck_store,
        get_http_client,
    )

    database = get_database()
    http_client = get_http_client()
    try:
        await get_deck_store().initialize()
        if settings.database_url.startswith("sqlite"):
            await database.create_schema()
        purge_local_temp_files()
        yield
    finally:
        shutdown_error: BaseException | None = None
        try:
            await database.dispose()
        except BaseException as exc:
            shutdown_error = exc
        try:
            if not http_client.is_closed:
                await http_client.aclose()
        except BaseException as exc:
            if shutdown_error is None:
                shutdown_error = exc
        try:
            await close_deck_file_storage()
        except BaseException as exc:
            if shutdown_error is None:
                shutdown_error = exc
        for clear_cache in (
            get_deck_version_service.cache_clear,
            get_deck_file_storage.cache_clear,
            get_deck_repository.cache_clear,
            get_onlyoffice_service.cache_clear,
            get_database.cache_clear,
            get_http_client.cache_clear,
        ):
            try:
                clear_cache()
            except BaseException as exc:
                if shutdown_error is None:
                    shutdown_error = exc
        if shutdown_error is not None:
            raise shutdown_error


app = FastAPI(
    title="SlideForge API",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

register_error_handlers(app)
register_rate_limiter(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

APP_VERSION = "1.0.0"


@app.middleware("http")
async def add_api_version_header(request, call_next):
    response = await call_next(request)
    response.headers["X-API-Version"] = APP_VERSION
    return response


app.include_router(v2.router, prefix="/api/v2", tags=["v2"])
app.include_router(generate.router, prefix="/api/v1", tags=["generate"])
app.include_router(refine.router, prefix="/api/v1", tags=["refine"])
app.include_router(export.router, prefix="/api/v1", tags=["export"])
app.include_router(uploads.router, prefix="/api/v1", tags=["uploads"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(decks.router, prefix="/api/v1", tags=["decks"])
app.include_router(preview.router, prefix="/api/v1", tags=["preview"])
app.include_router(onlyoffice.router, prefix="/api/v1", tags=["onlyoffice"])

def purge_local_temp_files() -> dict[str, int]:
    return {
        "exports": StorageService().purge_expired(settings.signed_url_expiry_minutes * 60),
        "uploads": UploadService().purge_expired(settings.session_ttl_minutes * 60),
    }


@app.get("/api/v1/download/{filename}")
async def download_export(filename: str):
    path = StorageService().get_local_path(filename, max_age_seconds=settings.signed_url_expiry_minutes * 60)
    if path is None:
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="SlideForge-Presentation.pptx",
        content_disposition_type="attachment",
    )

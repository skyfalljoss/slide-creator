import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.errors import ConfigurationError
from app.middleware.error_handler import register_error_handlers
from app.middleware.rate_limit import register_rate_limiter
from app.routers import generate, health, refine, export, uploads
from app.services.platform.storage import StorageService
from app.services.platform.uploads import UploadService


def _validate_config() -> None:
    if settings.ai_provider == "gemini" and not settings.gemini_api_key:
        raise ConfigurationError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
    if settings.session_provider == "redis" and (not settings.upstash_redis_rest_url or not settings.upstash_redis_rest_token):
        raise ConfigurationError("UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are required when SESSION_PROVIDER=redis")
    if settings.storage_provider == "gcs" and not settings.gcs_bucket:
        raise ConfigurationError("GCS_BUCKET is required when STORAGE_PROVIDER=gcs")


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
    purge_local_temp_files()
    yield


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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router, prefix="/api/v1", tags=["generate"])
app.include_router(refine.router, prefix="/api/v1", tags=["refine"])
app.include_router(export.router, prefix="/api/v1", tags=["export"])
app.include_router(uploads.router, prefix="/api/v1", tags=["uploads"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])

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

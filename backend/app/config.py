from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

from app.errors import ConfigurationError


class Settings(BaseSettings):
    gcp_project_id: str = "slideforge-dev"
    gcp_region: str = "us-central1"
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_key: str = ""
    gcs_bucket: str = "slideforge-temp"
    ai_provider: str = "local"
    dlp_provider: str = "local"
    storage_provider: Literal["local", "gcs"] = "local"
    local_export_dir: str = ".exports"
    local_upload_dir: str = ".uploads"
    max_upload_bytes: int = 5_000_000
    allowed_upload_extensions: list[str] = [".csv", ".xlsx"]
    api_base_url: str = ""
    audit_enabled: bool = True
    session_ttl_minutes: int = 30
    signed_url_expiry_minutes: int = 30
    deck_db_path: str = ".data/decks.db"
    database_url: str = "sqlite+aiosqlite:///.data/deck_versions.db"
    local_deck_file_dir: str = ".data/deck-files"
    onlyoffice_enabled: bool = False
    onlyoffice_public_url: str = "http://localhost:8080"
    onlyoffice_internal_url: str = "http://onlyoffice"
    onlyoffice_api_url: str = "http://host.docker.internal:8000"
    onlyoffice_jwt_secret: str = ""
    onlyoffice_file_token_ttl_seconds: int = Field(default=300, gt=0)
    onlyoffice_callback_token_ttl_seconds: int = Field(
        default=604_800, gt=0, le=2_592_000
    )
    onlyoffice_max_file_bytes: int = Field(
        default=50_000_000, gt=0, le=500_000_000
    )
    deck_version_retention: int = Field(default=5, ge=1, le=100)
    max_prompt_length: int = 5000
    citi_sso_enabled: bool = False
    allowed_origins: list[str] = ["http://localhost:5173"]
    allowed_origin_regex: str | None = r"^http://(?:localhost|127\.0\.0\.1)(?::\d+)?$"
    risk_disclosure: str = "Confidential. This material is for discussion purposes only and is not a guarantee of future results."
    citi_logo_path: str | None = "app/templates/citi_logo.png"
    sample_template_path: str = "app/templates/Citi PPTW Format - Sample Investment Banking Presentation.pptx"
    cloudflare_image_worker_url: str = ""
    cloudflare_image_worker_api_key: str = ""
    cloudflare_image_worker_model: str = "@cf/black-forest-labs/flux-1-schnell"
    image_mock_enabled: bool = True
    # Optional stock-photo source (Pexels). When a key is set, slide images are
    # sourced from stock photos and fall back to AI generation on miss/error.
    stock_photos_provider: str = "pexels"
    stock_photos_api_key: str = ""
    session_provider: str = "local"
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    rate_limit_generate: str = "10/minute"
    rate_limit_export: str = "30/minute"
    rate_limit_uploads: str = "60/minute"
    log_format: str = "console"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()


def validate_settings(configured: Settings) -> None:
    if configured.ai_provider == "gemini" and not configured.gemini_api_key:
        raise ConfigurationError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
    if configured.session_provider == "redis" and (
        not configured.upstash_redis_rest_url or not configured.upstash_redis_rest_token
    ):
        raise ConfigurationError(
            "UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are required when SESSION_PROVIDER=redis"
        )
    if configured.storage_provider == "gcs" and not configured.gcs_bucket:
        raise ConfigurationError("GCS_BUCKET is required when STORAGE_PROVIDER=gcs")
    if configured.onlyoffice_enabled and not configured.onlyoffice_jwt_secret:
        raise ConfigurationError("ONLYOFFICE_JWT_SECRET is required when ONLYOFFICE_ENABLED=true")

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gcp_project_id: str = "slideforge-dev"
    gcp_region: str = "us-central1"
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_key: str = ""
    gcs_bucket: str = "slideforge-temp"
    ai_provider: str = "local"
    dlp_provider: str = "local"
    storage_provider: str = "local"
    local_export_dir: str = ".exports"
    local_upload_dir: str = ".uploads"
    max_upload_bytes: int = 5_000_000
    allowed_upload_extensions: list[str] = [".csv", ".xlsx"]
    api_base_url: str = ""
    audit_enabled: bool = True
    session_ttl_minutes: int = 30
    signed_url_expiry_minutes: int = 30
    max_prompt_length: int = 5000
    citi_sso_enabled: bool = False
    allowed_origins: list[str] = ["http://localhost:5173"]
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

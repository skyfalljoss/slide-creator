from functools import lru_cache

import httpx

from app.config import settings
from app.services.platform.audit import AuditService
from app.services.platform.dlp import DlpService
from app.services.platform.session import LocalSessionStore, SessionStore
from app.services.platform.storage import StorageService
from app.services.generation.gemini import GeminiService
from app.services.generation.gemini_api import GeminiApiService
from app.services.platform.deck_store import DeckStore
from app.services.presentation.pptx_preview import PptxPreviewService


_audit_service = AuditService()


@lru_cache
def get_generator_service():
    if settings.ai_provider == "local":
        return GeminiService()
    if settings.ai_provider == "gemini":
        return GeminiApiService()
    raise NotImplementedError(f"{settings.ai_provider} provider is not implemented")


@lru_cache
def get_dlp_service() -> DlpService:
    return DlpService()


@lru_cache
def get_storage_service() -> StorageService:
    if settings.storage_provider == "gcs":
        from app.services.platform.storage import GCSStorageBackend
        return GCSStorageBackend()  # type: ignore[return-value]
    return StorageService()


@lru_cache
def get_session_store() -> SessionStore:
    if settings.session_provider == "redis":
        client = httpx.Client(
            base_url=settings.upstash_redis_rest_url,
            headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
            timeout=5.0,
        )
        from app.services.platform.session import RedisSessionStore
        return RedisSessionStore(client=client)
    return LocalSessionStore()


@lru_cache
def get_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))


def get_audit_service() -> AuditService:
    return _audit_service


_deck_store: DeckStore | None = None


def get_deck_store() -> DeckStore:
    global _deck_store
    if _deck_store is None:
        _deck_store = DeckStore(settings.deck_db_path)
    return _deck_store


@lru_cache
def get_preview_service() -> PptxPreviewService:
    return PptxPreviewService()

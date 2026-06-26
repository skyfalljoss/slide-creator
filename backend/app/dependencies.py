from functools import lru_cache

from app.config import settings
from app.services.platform.audit import AuditService
from app.services.platform.dlp import DlpService
from app.services.platform.session import LocalSessionStore, SessionStore
from app.services.platform.storage import StorageService
from app.services.generation.gemini import GeminiService
from app.services.generation.gemini_api import GeminiApiService


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
    return StorageService()


@lru_cache
def get_session_store() -> SessionStore:
    if settings.session_provider == "redis":
        raise NotImplementedError("Redis session store — implemented in Phase 2")
    return LocalSessionStore()


def get_audit_service() -> AuditService:
    return _audit_service

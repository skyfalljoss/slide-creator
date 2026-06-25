from app.config import settings
from app.services.audit import AuditService
from app.services.dlp import DlpService
from app.services.gemini import GeminiService
from app.services.gemini_api import GeminiApiService
from app.services.storage import StorageService


_audit_service = AuditService()


def get_generator_service() -> GeminiService:
    if settings.ai_provider == "local":
        return GeminiService()
    if settings.ai_provider == "gemini":
        return GeminiApiService()
    raise NotImplementedError(f"{settings.ai_provider} provider is not implemented")


def get_dlp_service() -> DlpService:
    if settings.dlp_provider != "local":
        raise NotImplementedError(f"{settings.dlp_provider} provider is not implemented")
    return DlpService()


def get_storage_service() -> StorageService:
    if settings.storage_provider != "local":
        raise NotImplementedError(f"{settings.storage_provider} provider is not implemented")
    return StorageService()


def get_audit_service() -> AuditService:
    return _audit_service

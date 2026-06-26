import pytest

from app.config import settings
from app.dependencies import get_audit_service, get_dlp_service, get_generator_service, get_storage_service


def test_provider_factories_return_local_defaults():
    assert get_generator_service().__class__.__name__ == "GeminiService"
    assert get_dlp_service().__class__.__name__ == "DlpService"
    assert get_storage_service().__class__.__name__ == "StorageService"
    assert get_audit_service().__class__.__name__ == "AuditService"


def test_audit_provider_returns_shared_instance():
    assert get_audit_service() is get_audit_service()


def test_generator_provider_fails_closed_for_unsupported_non_local(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ai_provider", "vertex")
    get_generator_service.cache_clear()
    try:
        with pytest.raises(NotImplementedError, match="vertex provider is not implemented"):
            get_generator_service()
    finally:
        monkeypatch.setattr(settings, "ai_provider", "local")
        get_generator_service.cache_clear()


def test_generator_provider_returns_gemini_api_service(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    get_generator_service.cache_clear()
    try:
        assert get_generator_service().__class__.__name__ == "GeminiApiService"
    finally:
        monkeypatch.setattr(settings, "ai_provider", "local")
        get_generator_service.cache_clear()

import pytest

from app.dependencies import (
    get_generator_service,
    get_dlp_service,
    get_storage_service,
    get_session_store,
    get_audit_service,
)
from app.config import settings


def test_get_generator_service_returns_local_by_default():
    svc = get_generator_service()
    assert svc.__class__.__name__ == "GeminiService"


def test_get_generator_service_returns_gemini_api(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    get_generator_service.cache_clear()
    try:
        svc = get_generator_service()
        assert svc.__class__.__name__ == "GeminiApiService"
    finally:
        monkeypatch.setattr(settings, "ai_provider", "local")
        get_generator_service.cache_clear()


def test_get_dlp_service_returns_local():
    svc = get_dlp_service()
    assert svc.__class__.__name__ == "DlpService"


def test_get_storage_service_returns_local():
    svc = get_storage_service()
    assert svc.__class__.__name__ == "StorageService"


def test_get_session_store_returns_local():
    store = get_session_store()
    assert store.__class__.__name__ == "LocalSessionStore"


def test_get_audit_service_returns_shared_instance():
    assert get_audit_service() is get_audit_service()


def test_get_generator_service_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "vertex")
    get_generator_service.cache_clear()
    try:
        with pytest.raises(NotImplementedError, match="vertex"):
            get_generator_service()
    finally:
        monkeypatch.setattr(settings, "ai_provider", "local")
        get_generator_service.cache_clear()

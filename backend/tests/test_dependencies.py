from unittest.mock import Mock

import pytest

from app.dependencies import (
    get_database,
    get_deck_file_storage,
    get_deck_repository,
    get_deck_version_service,
    get_generator_service,
    get_dlp_service,
    get_onlyoffice_service,
    get_storage_service,
    get_session_store,
    get_audit_service,
)
from app.config import settings
from app.services.platform.deck_repository import DeckRepository
from app.services.platform.deck_files import LocalDeckFileStorage
from app.services.platform.deck_versions import DeckVersionService


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


async def test_database_and_repository_are_cached_and_resettable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        settings,
        "database_url",
        f"sqlite+aiosqlite:///{tmp_path / 'repository.db'}",
    )
    get_deck_repository.cache_clear()
    get_database.cache_clear()
    database = get_database()
    try:
        repository = get_deck_repository()
        assert database is get_database()
        assert repository is get_deck_repository()
        assert isinstance(repository, DeckRepository)
        assert repository._database is database
    finally:
        get_deck_repository.cache_clear()
        get_database.cache_clear()
        await database.dispose()


def test_get_deck_file_storage_returns_cached_local_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_provider", "local")
    monkeypatch.setattr(settings, "local_deck_file_dir", str(tmp_path))
    get_deck_file_storage.cache_clear()
    try:
        storage = get_deck_file_storage()
        assert isinstance(storage, LocalDeckFileStorage)
        assert storage.root == tmp_path
        assert storage is get_deck_file_storage()
    finally:
        get_deck_file_storage.cache_clear()


def test_get_deck_file_storage_selects_gcs_without_network(monkeypatch):
    sentinel = object()
    factory = Mock(return_value=sentinel)
    monkeypatch.setattr(settings, "storage_provider", "gcs")
    monkeypatch.setattr(settings, "gcs_bucket", "deck-bucket")
    monkeypatch.setattr("app.dependencies.GCSDeckFileStorage", factory)
    get_deck_file_storage.cache_clear()
    try:
        assert get_deck_file_storage() is sentinel
        factory.assert_called_once_with("deck-bucket")
    finally:
        get_deck_file_storage.cache_clear()


def test_get_deck_version_service_is_cached_and_uses_configured_dependencies(monkeypatch):
    repository = object()
    storage = object()
    monkeypatch.setattr("app.dependencies.get_deck_repository", lambda: repository)
    monkeypatch.setattr("app.dependencies.get_deck_file_storage", lambda: storage)
    get_deck_version_service.cache_clear()
    try:
        service = get_deck_version_service()
        assert isinstance(service, DeckVersionService)
        assert service is get_deck_version_service()
        assert service._repository is repository
        assert service._storage is storage
        assert service._sample_template_path == settings.sample_template_path
        assert service._max_file_bytes == settings.onlyoffice_max_file_bytes
        assert service._retention == settings.deck_version_retention
    finally:
        get_deck_version_service.cache_clear()


def test_get_onlyoffice_service_uses_callback_token_lifetime(monkeypatch):
    monkeypatch.setattr(settings, "onlyoffice_callback_token_ttl_seconds", 1234)
    get_onlyoffice_service.cache_clear()
    try:
        service = get_onlyoffice_service()
        assert service._callback_token_ttl_seconds == 1234
    finally:
        get_onlyoffice_service.cache_clear()

from functools import lru_cache
from unittest.mock import AsyncMock, Mock

import pytest

from app import dependencies
from app.config import settings
from app.main import app, lifespan


@pytest.mark.parametrize(
    ("database_url", "expected_schema_calls"),
    [
        ("sqlite+aiosqlite:///:memory:", 1),
        ("postgresql+asyncpg://localhost/slideforge", 0),
    ],
)
async def test_lifespan_skips_legacy_store_and_manages_new_resources(
    monkeypatch,
    database_url,
    expected_schema_calls,
):
    database = Mock(create_schema=AsyncMock(), dispose=AsyncMock())
    legacy_provider = Mock()
    http_client = Mock(aclose=AsyncMock(), is_closed=False)
    monkeypatch.setattr(settings, "database_url", database_url)
    monkeypatch.setattr(dependencies, "get_database", lambda: database)
    monkeypatch.setattr(dependencies, "get_deck_store", legacy_provider)
    monkeypatch.setattr(dependencies, "get_http_client", lambda: http_client)
    monkeypatch.setattr(dependencies.get_deck_repository, "cache_clear", Mock())
    monkeypatch.setattr(dependencies.get_deck_file_storage, "cache_clear", Mock())
    monkeypatch.setattr(dependencies.get_deck_version_service, "cache_clear", Mock())
    monkeypatch.setattr(dependencies.get_onlyoffice_service, "cache_clear", Mock())
    monkeypatch.setattr(dependencies, "close_deck_file_storage", AsyncMock())
    monkeypatch.setattr(dependencies.get_database, "cache_clear", Mock(), raising=False)
    monkeypatch.setattr(dependencies.get_http_client, "cache_clear", Mock(), raising=False)
    monkeypatch.setattr("app.main.purge_local_temp_files", Mock())

    async with lifespan(app):
        legacy_provider.assert_not_called()
        assert database.create_schema.await_count == expected_schema_calls

    database.dispose.assert_awaited_once()
    http_client.aclose.assert_awaited_once()
    dependencies.get_deck_file_storage.cache_clear.assert_called_once()
    dependencies.get_deck_version_service.cache_clear.assert_called_once()
    dependencies.get_onlyoffice_service.cache_clear.assert_called_once()
    dependencies.close_deck_file_storage.assert_awaited_once()


async def test_lifespan_does_not_close_an_already_closed_http_client(monkeypatch):
    database = Mock(create_schema=AsyncMock(), dispose=AsyncMock())
    legacy_store = Mock(initialize=AsyncMock())
    http_client = Mock(aclose=AsyncMock(), is_closed=True)
    monkeypatch.setattr(settings, "database_url", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(dependencies, "get_database", lambda: database)
    monkeypatch.setattr(dependencies, "get_deck_store", lambda: legacy_store)
    monkeypatch.setattr(dependencies, "get_http_client", lambda: http_client)
    monkeypatch.setattr(dependencies.get_deck_repository, "cache_clear", Mock())
    monkeypatch.setattr(dependencies.get_database, "cache_clear", Mock(), raising=False)
    monkeypatch.setattr(dependencies.get_http_client, "cache_clear", Mock(), raising=False)
    monkeypatch.setattr("app.main.purge_local_temp_files", Mock())

    async with lifespan(app):
        pass

    http_client.aclose.assert_not_awaited()
    database.dispose.assert_awaited_once()


async def test_lifespan_closes_http_client_even_if_database_disposal_fails(monkeypatch):
    database = Mock(
        create_schema=AsyncMock(),
        dispose=AsyncMock(side_effect=RuntimeError("dispose failed")),
    )
    legacy_store = Mock(initialize=AsyncMock())
    http_client = Mock(aclose=AsyncMock(), is_closed=False)
    monkeypatch.setattr(settings, "database_url", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(dependencies, "get_database", lambda: database)
    monkeypatch.setattr(dependencies, "get_deck_store", lambda: legacy_store)
    monkeypatch.setattr(dependencies, "get_http_client", lambda: http_client)
    monkeypatch.setattr(dependencies.get_deck_repository, "cache_clear", Mock())
    monkeypatch.setattr(dependencies.get_database, "cache_clear", Mock(), raising=False)
    monkeypatch.setattr(dependencies.get_http_client, "cache_clear", Mock(), raising=False)
    monkeypatch.setattr("app.main.purge_local_temp_files", Mock())

    with pytest.raises(RuntimeError, match="dispose failed"):
        async with lifespan(app):
            pass

    http_client.aclose.assert_awaited_once()


async def test_lifespan_preserves_first_shutdown_error_and_attempts_all_cleanup(monkeypatch):
    first_error = RuntimeError("database dispose failed")
    database = Mock(
        create_schema=AsyncMock(),
        dispose=AsyncMock(side_effect=first_error),
    )
    legacy_store = Mock(initialize=AsyncMock())
    http_client = Mock(
        aclose=AsyncMock(side_effect=RuntimeError("http close failed")),
        is_closed=False,
    )
    close_storage = AsyncMock(side_effect=RuntimeError("gcs close failed"))
    monkeypatch.setattr(settings, "database_url", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(dependencies, "get_database", lambda: database)
    monkeypatch.setattr(dependencies, "get_deck_store", lambda: legacy_store)
    monkeypatch.setattr(dependencies, "get_http_client", lambda: http_client)
    monkeypatch.setattr(dependencies, "close_deck_file_storage", close_storage)
    monkeypatch.setattr(dependencies.get_deck_repository, "cache_clear", Mock())
    monkeypatch.setattr(dependencies.get_deck_file_storage, "cache_clear", Mock())
    monkeypatch.setattr(dependencies.get_deck_version_service, "cache_clear", Mock())
    monkeypatch.setattr(dependencies.get_database, "cache_clear", Mock(), raising=False)
    monkeypatch.setattr(dependencies.get_http_client, "cache_clear", Mock(), raising=False)
    monkeypatch.setattr("app.main.purge_local_temp_files", Mock())

    with pytest.raises(RuntimeError, match="database dispose failed") as raised:
        async with lifespan(app):
            pass

    assert raised.value is first_error
    http_client.aclose.assert_awaited_once()
    close_storage.assert_awaited_once()
    dependencies.get_database.cache_clear.assert_called_once()


async def test_lifespan_clears_caches_for_fresh_resources_on_restart(monkeypatch):
    databases = []
    http_clients = []

    @lru_cache
    def database_factory():
        database = Mock(create_schema=AsyncMock(), dispose=AsyncMock())
        databases.append(database)
        return database

    @lru_cache
    def http_client_factory():
        client = Mock(aclose=AsyncMock(), is_closed=False)
        http_clients.append(client)
        return client

    legacy_store = Mock(initialize=AsyncMock())
    monkeypatch.setattr(settings, "database_url", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(dependencies, "get_database", database_factory)
    monkeypatch.setattr(dependencies, "get_deck_store", lambda: legacy_store)
    monkeypatch.setattr(dependencies, "get_http_client", http_client_factory)
    monkeypatch.setattr(dependencies.get_deck_repository, "cache_clear", Mock())
    monkeypatch.setattr("app.main.purge_local_temp_files", Mock())

    async with lifespan(app):
        assert dependencies.get_database() is databases[0]
        assert dependencies.get_http_client() is http_clients[0]
    async with lifespan(app):
        assert dependencies.get_database() is databases[1]
        assert dependencies.get_http_client() is http_clients[1]

    assert databases[0] is not databases[1]
    assert http_clients[0] is not http_clients[1]
    for database in databases:
        database.dispose.assert_awaited_once()
    for client in http_clients:
        client.aclose.assert_awaited_once()

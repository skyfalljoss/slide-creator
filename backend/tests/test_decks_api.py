from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app import dependencies
from app.main import app
from app.services.platform.database import Database
from app.services.platform.deck_files import LocalDeckFileStorage
from app.services.platform.deck_repository import DeckRepository
from app.services.platform.deck_versions import DeckVersionService


def _slides(title: str = "Cover") -> list[dict]:
    return [
        {
            "index": 1,
            "title": title,
            "bullets": [],
            "notes": "",
            "layout": "title",
        }
    ]


@pytest.fixture
async def deck_api(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'decks.db'}")
    await database.create_schema()
    repository = DeckRepository(database)
    storage = LocalDeckFileStorage(tmp_path / "objects")
    versions = DeckVersionService(
        repository=repository,
        storage=storage,
        sample_template_path=None,
        max_file_bytes=20 * 1024 * 1024,
        retention=5,
    )
    app.dependency_overrides[dependencies.get_deck_repository] = lambda: repository
    app.dependency_overrides[dependencies.get_deck_file_storage] = lambda: storage
    app.dependency_overrides[dependencies.get_deck_version_service] = lambda: versions
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, repository, storage
    app.dependency_overrides.clear()
    await database.dispose()


async def _create(client: AsyncClient, *, owner: str = "alice", name: str = "Deck"):
    return await client.post(
        "/api/v1/decks",
        headers={"x-user-id": owner},
        json={
            "name": name,
            "deck_type": "sales_9",
            "theme": "minimalist",
            "aspect_ratio": "16:9",
            "slides": _slides(),
        },
    )


@pytest.mark.asyncio
async def test_legacy_create_list_and_get_use_persisted_owner_scoped_decks(deck_api):
    client, repository, _storage = deck_api
    response = await _create(client)

    assert response.status_code == 200
    deck_id = response.json()["id"]
    persisted = await repository.get(deck_id, "alice")
    assert persisted is not None
    assert persisted.current_version is not None
    assert persisted.current_version.version_number == 1

    listed = await client.get("/api/v1/decks", headers={"x-user-id": "alice"})
    assert listed.status_code == 200
    assert listed.json()["decks"][0]["slide_count"] == 1

    detail = await client.get(
        f"/api/v1/decks/{deck_id}", headers={"x-user-id": "alice"}
    )
    assert detail.status_code == 200
    assert detail.json()["slides"][0]["title"] == "Cover"


@pytest.mark.asyncio
async def test_cross_user_cannot_read_update_rename_or_delete(deck_api):
    client, _repository, _storage = deck_api
    deck_id = (await _create(client)).json()["id"]
    headers = {"x-user-id": "bob"}

    responses = [
        await client.get(f"/api/v1/decks/{deck_id}", headers=headers),
        await client.put(
            f"/api/v1/decks/{deck_id}",
            headers=headers,
            json={"slides": _slides("Stolen")},
        ),
        await client.patch(
            f"/api/v1/decks/{deck_id}", headers=headers, json={"name": "Stolen"}
        ),
        await client.delete(f"/api/v1/decks/{deck_id}", headers=headers),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404, 404]


@pytest.mark.asyncio
async def test_legacy_update_persists_slides_before_rename(deck_api):
    client, repository, _storage = deck_api
    deck_id = (await _create(client, name="Original")).json()["id"]

    response = await client.put(
        f"/api/v1/decks/{deck_id}",
        headers={"x-user-id": "alice"},
        json={"name": "Renamed", "slides": _slides("Updated")},
    )

    assert response.status_code == 200
    deck = await repository.get(deck_id, "alice")
    assert deck is not None
    assert deck.name == "Renamed"
    assert deck.current_version is not None
    assert deck.current_version.version_number == 2
    assert deck.current_version.source == "generated"
    assert deck.generation_payload["slides"][0]["title"] == "Updated"


@pytest.mark.asyncio
async def test_delete_commits_database_before_best_effort_object_cleanup(deck_api):
    client, repository, storage = deck_api
    deck_id = (await _create(client)).json()["id"]
    deck = await repository.get(deck_id, "alice")
    assert deck is not None and deck.current_version is not None
    key = deck.current_version.storage_key
    real_delete = storage.delete
    storage.delete = AsyncMock(side_effect=OSError("storage unavailable"))

    response = await client.delete(
        f"/api/v1/decks/{deck_id}", headers={"x-user-id": "alice"}
    )

    assert response.status_code == 200
    assert await repository.get(deck_id, "alice") is None
    storage.delete.assert_awaited_once_with(key)
    assert await storage.exists(key) is True
    storage.delete = real_delete


@pytest.mark.asyncio
async def test_list_search_and_empty_name_validation(deck_api):
    client, _repository, _storage = deck_api
    await _create(client, name="Alpha Deck")
    await _create(client, name="Beta Deck")

    response = await client.get(
        "/api/v1/decks?q=Alpha", headers={"x-user-id": "alice"}
    )
    assert response.status_code == 200
    assert [deck["name"] for deck in response.json()["decks"]] == ["Alpha Deck"]

    invalid = await client.post(
        "/api/v1/decks",
        headers={"x-user-id": "alice"},
        json={
            "name": "",
            "deck_type": "sales_9",
            "theme": "minimalist",
            "aspect_ratio": "16:9",
            "slides": [],
        },
    )
    assert invalid.status_code == 422

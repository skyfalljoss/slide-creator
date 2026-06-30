import asyncio
import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from starlette.requests import Request

from app import dependencies
from app.main import app
from app.services.platform.database import Database
from app.services.platform.deck_files import LocalDeckFileStorage
from app.services.platform.deck_repository import DeckRepository
from app.services.platform.deck_versions import DeckVersionService
from app.routers.decks import delete_deck


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
    repository = DeckRepository(database, lock_dir=tmp_path / "locks")
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
async def test_legacy_update_rolls_back_version_and_name_when_atomic_write_fails(
    deck_api,
):
    client, repository, storage = deck_api
    deck_id = (await _create(client, name="Original")).json()["id"]
    original = await repository.get(deck_id, "alice")
    assert original is not None and original.current_version is not None
    original_key = original.current_version.storage_key

    def reject_name_update(
        _connection, _cursor, statement, _parameters, _context, _many
    ):
        if statement.lstrip().upper().startswith("UPDATE DECKS SET NAME"):
            raise RuntimeError("rename write failed")

    event.listen(
        repository._database.engine.sync_engine,
        "before_cursor_execute",
        reject_name_update,
    )
    try:
        response = await client.put(
            f"/api/v1/decks/{deck_id}",
            headers={"x-user-id": "alice"},
            json={"name": "Renamed", "slides": _slides("Updated")},
        )
    finally:
        event.remove(
            repository._database.engine.sync_engine,
            "before_cursor_execute",
            reject_name_update,
        )

    assert response.status_code == 500
    deck = await repository.get(deck_id, "alice")
    assert deck is not None and deck.current_version is not None
    assert deck.name == "Original"
    assert deck.current_version.id == original.current_version.id
    assert [version.id for version in await repository.list_versions(deck_id, "alice")] == [
        original.current_version.id
    ]
    assert await storage.list_keys(f"decks/{deck_id}/") == [original_key]


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["put", "patch"])
async def test_rename_rejects_whitespace_only_name(deck_api, method):
    client, _repository, _storage = deck_api
    deck_id = (await _create(client)).json()["id"]

    response = await getattr(client, method)(
        f"/api/v1/decks/{deck_id}",
        headers={"x-user-id": "alice"},
        json={"name": "   "},
    )

    assert response.status_code == 422


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


class _PausedDeleteStorage(LocalDeckFileStorage):
    def __init__(self, root):
        super().__init__(root)
        self.delete_entered = asyncio.Event()
        self.release_delete = asyncio.Event()

    async def delete(self, key):
        self.delete_entered.set()
        await self.release_delete.wait()
        await super().delete(key)


async def _delete_reimport_fixture(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'delete-race.db'}"
    first_database = Database(url)
    second_database = Database(url)
    await first_database.create_schema()
    lock_dir = tmp_path / "locks"
    deleting_repository = DeckRepository(first_database, lock_dir=lock_dir)
    writing_repository = DeckRepository(second_database, lock_dir=lock_dir)
    storage = _PausedDeleteStorage(tmp_path / "objects")
    key = "decks/reimport/versions/version-1.pptx"
    content = b"immutable-pptx"
    await storage.put(key, content)
    await deleting_repository.create_with_initial_version(
        deck_id="reimport",
        version_id="version-1",
        owner_id="alice",
        name="Original",
        deck_type="sales",
        theme="minimalist",
        aspect_ratio="16:9",
        generation_payload={"slides": []},
        storage_key=key,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )
    request = Request(
        {"type": "http", "method": "DELETE", "path": "/", "headers": [(b"x-user-id", b"alice")]}
    )
    return first_database, second_database, deleting_repository, writing_repository, storage, request, key, content


async def _reimport(repository, storage, key, content):
    async with repository.storage_key_guard(key) as session:
        try:
            await storage.put(key, content)
        except FileExistsError:
            pass
        return await repository.import_with_initial_version(
            deck_id="reimport",
            version_id="version-1",
            owner_id="alice",
            name="Reimported",
            deck_type="sales",
            theme="minimalist",
            aspect_ratio="16:9",
            generation_payload={"slides": []},
            storage_key=key,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            session=session,
        )


@pytest.mark.asyncio
async def test_delete_guard_prevents_reimport_metadata_pointing_to_deleted_object(tmp_path):
    fixture = await _delete_reimport_fixture(tmp_path)
    db1, db2, deleting, writing, storage, request, key, content = fixture
    try:
        deletion = asyncio.create_task(delete_deck("reimport", request, deleting, storage))
        await asyncio.wait_for(storage.delete_entered.wait(), 1)
        writer = asyncio.create_task(_reimport(writing, storage, key, content))
        await asyncio.sleep(0.05)
        assert writer.done() is False
        storage.release_delete.set()
        await deletion
        await writer
        assert await writing.storage_key_referenced(key)
        assert await storage.exists(key)
    finally:
        await db1.dispose()
        await db2.dispose()


@pytest.mark.asyncio
async def test_cancelled_delete_waits_for_object_delete_before_reimport(tmp_path):
    fixture = await _delete_reimport_fixture(tmp_path)
    db1, db2, deleting, writing, storage, request, key, content = fixture
    try:
        deletion = asyncio.create_task(delete_deck("reimport", request, deleting, storage))
        await asyncio.wait_for(storage.delete_entered.wait(), 1)
        writer = asyncio.create_task(_reimport(writing, storage, key, content))
        deletion.cancel()
        deletion.cancel()
        await asyncio.sleep(0.05)
        assert deletion.done() is False
        assert writer.done() is False
        storage.release_delete.set()
        with pytest.raises(asyncio.CancelledError):
            await deletion
        await writer
        assert await writing.storage_key_referenced(key)
        assert await storage.exists(key)
    finally:
        await db1.dispose()
        await db2.dispose()


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

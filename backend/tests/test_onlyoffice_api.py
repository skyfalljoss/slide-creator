from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app import dependencies
from app.main import app
from app.services.platform.deck_files import PPTX_CONTENT_TYPE
from app.services.platform.deck_repository import DeckRecord, DeckVersionRecord
from app.services.platform.onlyoffice import OnlyOfficeService


NOW = datetime(2030, 6, 26, 12, 0, tzinfo=timezone.utc)
SECRET = "test-secret-with-at-least-thirty-two-bytes"
PPTX_BYTES = b"PK\x03\x04private-presentation"


def _deck() -> DeckRecord:
    version = DeckVersionRecord(
        id="version-1",
        deck_id="deck-1",
        version_number=1,
        storage_key="decks/deck-1/versions/version-1.pptx",
        sha256="a" * 64,
        size_bytes=len(PPTX_BYTES),
        source="generated",
        created_by="alice",
        created_at=NOW,
    )
    return DeckRecord(
        id="deck-1",
        owner_id="alice",
        name="Private Deck",
        deck_type="sales_9",
        theme="minimalist",
        aspect_ratio="16:9",
        generation_payload=None,
        current_version_id=version.id,
        created_at=NOW,
        updated_at=NOW,
        current_version=version,
    )


class FakeRepository:
    async def get(self, deck_id: str, owner_id: str):
        if deck_id == "deck-1" and owner_id == "alice":
            return _deck()
        return None


class FakeStorage:
    def __init__(self):
        self.read_keys: list[str] = []

    async def read(self, key: str) -> bytes:
        self.read_keys.append(key)
        return PPTX_BYTES


@pytest.fixture
async def onlyoffice_client():
    service = OnlyOfficeService(
        public_url="http://localhost:8080",
        api_base_url="http://api:8000",
        jwt_secret=SECRET,
        file_token_ttl_seconds=300,
        now=lambda: NOW,
    )
    storage = FakeStorage()
    app.dependency_overrides[dependencies.get_onlyoffice_service] = lambda: service
    app.dependency_overrides[dependencies.get_deck_repository] = FakeRepository
    app.dependency_overrides[dependencies.get_deck_file_storage] = lambda: storage
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, service, storage
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_owner_receives_editor_config_and_private_pptx(onlyoffice_client):
    client, _service, storage = onlyoffice_client
    config_response = await client.get(
        "/api/v1/decks/deck-1/editor-config",
        headers={"x-user-id": "alice", "x-user-name": "Alice"},
    )

    assert config_response.status_code == 200
    body = config_response.json()
    assert body["document_server_url"] == "http://localhost:8080"
    assert body["config"]["editorConfig"]["user"] == {
        "id": "alice",
        "name": "Alice",
    }
    content_url = body["config"]["document"]["url"]
    token = parse_qs(urlparse(content_url).query)["token"][0]

    content_response = await client.get(
        f"/api/v1/decks/deck-1/content?token={token}"
    )

    assert content_response.status_code == 200
    assert content_response.content == PPTX_BYTES
    assert content_response.headers["content-type"] == PPTX_CONTENT_TYPE
    assert content_response.headers["content-disposition"] == "inline; filename=deck.pptx"
    assert content_response.headers["cache-control"] == "private, no-store"
    assert storage.read_keys == ["decks/deck-1/versions/version-1.pptx"]


@pytest.mark.asyncio
async def test_another_user_cannot_get_editor_config(onlyoffice_client):
    client, _service, _storage = onlyoffice_client

    response = await client.get(
        "/api/v1/decks/deck-1/editor-config", headers={"x-user-id": "bob"}
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_content_rejects_expired_token_before_storage_read(onlyoffice_client):
    client, _service, storage = onlyoffice_client
    token = jwt.encode(
        {
            "sub": "alice",
            "deck_id": "deck-1",
            "version_id": "version-1",
            "purpose": "content",
            "iat": int((NOW - timedelta(minutes=10)).timestamp()),
            "exp": int((NOW - timedelta(minutes=5)).timestamp()),
        },
        SECRET,
        algorithm="HS256",
    )

    response = await client.get(f"/api/v1/decks/deck-1/content?token={token}")

    assert response.status_code == 401
    assert storage.read_keys == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claims",
    [
        {"deck_id": "deck-2"},
        {"version_id": "version-2"},
        {"purpose": "callback"},
    ],
)
async def test_content_rejects_wrong_token_scope_before_storage_read(
    onlyoffice_client, claims
):
    client, service, storage = onlyoffice_client
    token = service.create_scoped_token(
        subject="alice",
        deck_id=claims.get("deck_id", "deck-1"),
        version_id=claims.get("version_id", "version-1"),
        purpose=claims.get("purpose", "content"),
    )

    response = await client.get(f"/api/v1/decks/deck-1/content?token={token}")

    assert response.status_code == 401
    assert storage.read_keys == []

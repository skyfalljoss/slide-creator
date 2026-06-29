import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from app import dependencies
from app.main import app
from app.routers.onlyoffice import download_deck, get_deck_content
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
        self.opened_keys: list[str] = []
        self.requested_chunk_sizes: list[int] = []
        self.closed = False
        self.close_calls = 0
        self.next_calls = 0

    async def read(self, key: str) -> bytes:
        raise AssertionError(f"content route must not buffer the whole object: {key}")

    async def open_stream(self, key: str, chunk_size: int):
        self.opened_keys.append(key)
        self.requested_chunk_sizes.append(chunk_size)
        storage = self

        class Stream:
            def __init__(self):
                self._chunks = iter((b"PK\x03\x04", b"private-", b"presentation"))

            def __aiter__(self):
                return self

            async def __anext__(self):
                storage.next_calls += 1
                try:
                    return next(self._chunks)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc

            async def aclose(self):
                storage.close_calls += 1
                storage.closed = True

        return Stream()


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
    assert storage.opened_keys == ["decks/deck-1/versions/version-1.pptx"]
    assert storage.requested_chunk_sizes == [256 * 1024]
    assert storage.closed is True
    assert storage.close_calls == 1


@pytest.mark.asyncio
async def test_direct_download_streams_current_pptx_and_closes_once(onlyoffice_client):
    client, _service, storage = onlyoffice_client

    response = await client.get(
        "/api/v1/decks/deck-1/download",
        headers={"x-user-id": "alice"},
    )

    assert response.status_code == 200
    assert response.content == PPTX_BYTES
    assert response.headers["content-disposition"] == (
        'attachment; filename="Private Deck.pptx"'
    )
    assert storage.opened_keys == ["decks/deck-1/versions/version-1.pptx"]
    assert storage.requested_chunk_sizes == [256 * 1024]
    assert storage.close_calls == 1


@pytest.mark.asyncio
async def test_direct_download_maps_missing_object_before_streaming(onlyoffice_client):
    client, _service, storage = onlyoffice_client

    async def missing_stream(_key: str, chunk_size: int):
        del chunk_size
        raise FileNotFoundError("missing")

    storage.open_stream = missing_stream
    response = await client.get(
        "/api/v1/decks/deck-1/download",
        headers={"x-user-id": "alice"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Deck content not found"}


def _download_scope() -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/decks/deck-1/download",
        "raw_path": b"/api/v1/decks/deck-1/download",
        "query_string": b"",
        "headers": [(b"x-user-id", b"alice")],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "root_path": "",
    }


async def _direct_download_response(storage: FakeStorage):
    return await download_deck(
        deck_id="deck-1",
        request=Request(_download_scope()),
        repository=FakeRepository(),
        storage=storage,
    )


@pytest.mark.asyncio
async def test_direct_download_closes_stream_when_headers_fail():
    storage = FakeStorage()
    response = await _direct_download_response(storage)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def fail_on_start(message):
        assert message["type"] == "http.response.start"
        raise RuntimeError("send failed")

    with pytest.raises(RuntimeError, match="send failed"):
        await response(_download_scope(), receive, fail_on_start)

    assert storage.next_calls == 0
    assert storage.close_calls == 1


@pytest.mark.asyncio
async def test_direct_download_closes_stream_when_cancelled_before_headers():
    storage = FakeStorage()
    response = await _direct_download_response(storage)
    entered = asyncio.Event()

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def block_start(message):
        assert message["type"] == "http.response.start"
        entered.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(response(_download_scope(), receive, block_start))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert storage.next_calls == 0
    assert storage.close_calls == 1


@pytest.mark.asyncio
async def test_editor_config_does_not_trust_host_header(onlyoffice_client):
    client, _service, _storage = onlyoffice_client

    response = await client.get(
        "/api/v1/decks/deck-1/editor-config",
        headers={"x-user-id": "alice", "host": "attacker.example"},
    )

    assert response.status_code == 200
    config = response.json()["config"]
    assert config["document"]["url"].startswith("http://api:8000/")
    assert config["editorConfig"]["callbackUrl"].startswith("http://api:8000/")
    assert "attacker.example" not in config["document"]["url"]
    assert "attacker.example" not in config["editorConfig"]["callbackUrl"]


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
    assert storage.opened_keys == []


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
    assert storage.opened_keys == []


@pytest.mark.asyncio
async def test_content_maps_missing_object_to_404(onlyoffice_client):
    client, service, storage = onlyoffice_client

    async def missing_stream(_key: str, chunk_size: int):
        del chunk_size
        raise FileNotFoundError("missing")

    storage.open_stream = missing_stream
    token = service.create_scoped_token(
        subject="alice",
        deck_id="deck-1",
        version_id="version-1",
        purpose="content",
    )

    response = await client.get(f"/api/v1/decks/deck-1/content?token={token}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_content_stream_closes_if_response_start_send_fails(onlyoffice_client):
    _client, service, storage = onlyoffice_client
    token = service.create_scoped_token(
        subject="alice",
        deck_id="deck-1",
        version_id="version-1",
        purpose="content",
    )
    response = await get_deck_content(
        deck_id="deck-1",
        token=token,
        repository=FakeRepository(),
        storage=storage,
        onlyoffice=service,
    )

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def fail_on_start(message):
        assert message["type"] == "http.response.start"
        raise RuntimeError("send failed")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/decks/deck-1/content",
        "raw_path": b"/api/v1/decks/deck-1/content",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "root_path": "",
    }

    with pytest.raises(RuntimeError, match="send failed"):
        await response(scope, receive, fail_on_start)

    assert storage.next_calls == 0
    assert storage.close_calls == 1
    assert storage.closed is True


@pytest.mark.asyncio
async def test_content_stream_closes_if_cancelled_during_response_start(
    onlyoffice_client,
):
    _client, service, storage = onlyoffice_client
    token = service.create_scoped_token(
        subject="alice",
        deck_id="deck-1",
        version_id="version-1",
        purpose="content",
    )
    response = await get_deck_content(
        deck_id="deck-1",
        token=token,
        repository=FakeRepository(),
        storage=storage,
        onlyoffice=service,
    )
    start_send_entered = asyncio.Event()

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def block_response_start(message):
        assert message["type"] == "http.response.start"
        start_send_entered.set()
        await asyncio.Event().wait()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/decks/deck-1/content",
        "raw_path": b"/api/v1/decks/deck-1/content",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "root_path": "",
    }
    response_task = asyncio.create_task(
        response(scope, receive, block_response_start)
    )
    await start_send_entered.wait()
    response_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await response_task

    assert storage.next_calls == 0
    assert storage.close_calls == 1
    assert storage.closed is True

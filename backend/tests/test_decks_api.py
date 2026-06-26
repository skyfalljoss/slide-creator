import os
import tempfile
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport

from app.dependencies import get_deck_store
from app.main import app
from app.services.platform.deck_store import DeckStore


@pytest.fixture
def tmp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
async def client(tmp_db_path: str):
    store = DeckStore(tmp_db_path)
    await store.initialize()
    app.dependency_overrides[get_deck_store] = lambda: store
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_save_and_list_decks(client: AsyncClient):
    slides = [
        {"index": 1, "title": "Cover", "bullets": [], "notes": "", "layout": "title"},
    ]
    save_resp = await client.post(
        "/api/v1/decks",
        json={
            "name": "API Test Deck",
            "deck_type": "sales_9",
            "theme": "minimalist",
            "aspect_ratio": "16:9",
            "slides": slides,
        },
    )
    assert save_resp.status_code == 200
    data = save_resp.json()
    assert "id" in data
    deck_id = data["id"]
    assert data["name"] == "API Test Deck"

    list_resp = await client.get("/api/v1/decks")
    assert list_resp.status_code == 200
    decks = list_resp.json()["decks"]
    assert len(decks) >= 1
    found = next((d for d in decks if d["id"] == deck_id), None)
    assert found is not None
    assert found["name"] == "API Test Deck"
    assert found["slide_count"] == 1


@pytest.mark.asyncio
async def test_get_deck_by_id(client: AsyncClient):
    slides = [
        {"index": 1, "title": "Cover", "bullets": [], "notes": "", "layout": "title"},
        {"index": 2, "title": "Overview", "bullets": ["Point A"], "notes": "N", "layout": "content"},
    ]
    save_resp = await client.post(
        "/api/v1/decks",
        json={
            "name": "Detail Test",
            "deck_type": "sales_9",
            "theme": "minimalist",
            "aspect_ratio": "16:9",
            "slides": slides,
        },
    )
    deck_id = save_resp.json()["id"]

    get_resp = await client.get(f"/api/v1/decks/{deck_id}")
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["name"] == "Detail Test"
    assert len(detail["slides"]) == 2
    assert detail["slides"][0]["title"] == "Cover"


@pytest.mark.asyncio
async def test_update_deck(client: AsyncClient):
    slides = [
        {"index": 1, "title": "Old", "bullets": [], "notes": "", "layout": "title"},
    ]
    save_resp = await client.post(
        "/api/v1/decks",
        json={
            "name": "Original",
            "deck_type": "sales_9",
            "theme": "minimalist",
            "aspect_ratio": "16:9",
            "slides": slides,
        },
    )
    deck_id = save_resp.json()["id"]

    new_slides = [
        {"index": 1, "title": "Renamed", "bullets": ["Updated bullet"], "notes": "", "layout": "title"},
    ]
    update_resp = await client.put(
        f"/api/v1/decks/{deck_id}",
        json={"name": "Renamed Deck", "slides": new_slides},
    )
    assert update_resp.status_code == 200
    assert "updated_at" in update_resp.json()

    get_resp = await client.get(f"/api/v1/decks/{deck_id}")
    detail = get_resp.json()
    assert detail["name"] == "Renamed Deck"
    assert detail["slides"][0]["title"] == "Renamed"


@pytest.mark.asyncio
async def test_delete_deck(client: AsyncClient):
    slides = [
        {"index": 1, "title": "Temp", "bullets": [], "notes": "", "layout": "title"},
    ]
    save_resp = await client.post(
        "/api/v1/decks",
        json={
            "name": "Delete Me",
            "deck_type": "sales_9",
            "theme": "minimalist",
            "aspect_ratio": "16:9",
            "slides": slides,
        },
    )
    deck_id = save_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/decks/{deck_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["ok"] is True

    get_resp = await client.get(f"/api/v1/decks/{deck_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_deck_404(client: AsyncClient):
    resp = await client.get("/api/v1/decks/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_decks_with_search(client: AsyncClient):
    slides = [
        {"index": 1, "title": "X", "bullets": [], "notes": "", "layout": "title"},
    ]
    await client.post(
        "/api/v1/decks",
        json={"name": "Alpha Deck", "deck_type": "sales_9", "theme": "minimalist", "aspect_ratio": "16:9", "slides": slides},
    )
    await client.post(
        "/api/v1/decks",
        json={"name": "Beta Deck", "deck_type": "sales_9", "theme": "minimalist", "aspect_ratio": "16:9", "slides": slides},
    )

    resp = await client.get("/api/v1/decks?q=Alpha")
    assert resp.status_code == 200
    decks = resp.json()["decks"]
    assert len(decks) == 1
    assert decks[0]["name"] == "Alpha Deck"


@pytest.mark.asyncio
async def test_save_deck_empty_name_returns_422(client: AsyncClient):
    resp = await client.post(
        "/api/v1/decks",
        json={"name": "", "deck_type": "sales_9", "theme": "minimalist", "aspect_ratio": "16:9", "slides": []},
    )
    assert resp.status_code == 422

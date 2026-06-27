import base64
import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_deck_store, get_preview_service
from app.main import app
from app.models.schemas import SlidePreviewResponse
from app.services.platform.deck_store import DeckStore
from app.services.presentation.pptx_preview import PreviewRendererUnavailable


PNG_BYTES = b"\x89PNG\r\n\x1a\napi-preview"


class FakePreviewService:
    def __init__(self, *, unavailable: bool = False):
        self.unavailable = unavailable
        self.calls: list[dict[str, object]] = []

    def render_deck_slide(self, **kwargs) -> SlidePreviewResponse:
        self.calls.append(kwargs)
        if int(kwargs["slide_index"]) > len(kwargs["slides"]):
            raise IndexError(f"Slide index {kwargs['slide_index']} is not available")
        if self.unavailable:
            raise PreviewRendererUnavailable("LibreOffice/soffice not found")
        return SlidePreviewResponse(
            deck_id=str(kwargs["deck_id"]),
            slide_index=int(kwargs["slide_index"]),
            image_b64=base64.b64encode(PNG_BYTES).decode("ascii"),
            width=1920,
            height=1080,
            updated_at=str(kwargs.get("updated_at") or ""),
        )


@pytest.fixture
def tmp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
async def preview_client(tmp_db_path: str):
    store = DeckStore(tmp_db_path)
    await store.initialize()
    service = FakePreviewService()
    app.dependency_overrides[get_deck_store] = lambda: store
    app.dependency_overrides[get_preview_service] = lambda: service
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, service
    app.dependency_overrides.clear()


async def _create_deck(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/decks",
        json={
            "name": "Preview Deck",
            "deck_type": "sales_9",
            "theme": "minimalist",
            "aspect_ratio": "16:9",
            "slides": [
                {"index": 1, "title": "Cover", "bullets": [], "notes": "", "layout": "title"},
                {"index": 2, "title": "Today's Discussion", "bullets": ["One"], "notes": "", "layout": "content"},
            ],
        },
    )
    assert resp.status_code == 200
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_get_deck_slide_preview(preview_client):
    client, service = preview_client
    deck_id = await _create_deck(client)

    resp = await client.get(f"/api/v1/decks/{deck_id}/preview?slide_index=2")

    assert resp.status_code == 200
    data = resp.json()
    assert data["deck_id"] == deck_id
    assert data["slide_index"] == 2
    assert base64.b64decode(data["image_b64"]) == PNG_BYTES
    assert data["width"] == 1920
    assert data["height"] == 1080
    assert service.calls[0]["theme"] == "minimalist"
    assert service.calls[0]["aspect_ratio"] == "16:9"


@pytest.mark.asyncio
async def test_get_deck_slide_preview_missing_deck_returns_404(preview_client):
    client, _service = preview_client

    resp = await client.get("/api/v1/decks/missing/preview?slide_index=1")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_deck_slide_preview_invalid_slide_returns_422(preview_client):
    client, _service = preview_client
    deck_id = await _create_deck(client)

    resp = await client.get(f"/api/v1/decks/{deck_id}/preview?slide_index=99")

    assert resp.status_code == 422
    assert "Slide index 99 is not available" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_deck_slide_preview_unavailable_returns_503(tmp_db_path: str):
    store = DeckStore(tmp_db_path)
    await store.initialize()
    service = FakePreviewService(unavailable=True)
    app.dependency_overrides[get_deck_store] = lambda: store
    app.dependency_overrides[get_preview_service] = lambda: service
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        deck_id = await _create_deck(client)
        resp = await client.get(f"/api/v1/decks/{deck_id}/preview?slide_index=1")

    app.dependency_overrides.clear()
    assert resp.status_code == 503
    assert "LibreOffice/soffice not found" in resp.json()["detail"]

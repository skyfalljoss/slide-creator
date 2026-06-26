from io import BytesIO

from httpx import AsyncClient, ASGITransport
from pptx import Presentation
import pytest

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_by_deck_id(client: AsyncClient):
    slides = [
        {"index": 1, "title": "Cover", "bullets": [], "notes": "", "layout": "title"},
        {"index": 2, "title": "Content", "bullets": ["Point"], "notes": "N", "layout": "content"},
    ]
    save_resp = await client.post(
        "/api/v1/decks",
        json={"name": "Export Deck", "deck_type": "sales_9", "theme": "minimalist", "aspect_ratio": "16:9", "slides": slides},
    )
    deck_id = save_resp.json()["id"]

    export_resp = await client.post("/api/v1/export", json={"deck_id": deck_id})
    assert export_resp.status_code == 200
    data = export_resp.json()
    assert data["download_url"].startswith("http://test/api/v1/download/")

    download = await client.get(data["download_url"].replace("http://test", ""))
    assert download.status_code == 200
    assert download.content.startswith(b"PK")
    prs = Presentation(BytesIO(download.content))
    assert len(prs.slides) >= 2


@pytest.mark.asyncio
async def test_export_no_session_or_deck_id_returns_422(client: AsyncClient):
    resp = await client.post("/api/v1/export", json={})
    assert resp.status_code == 422

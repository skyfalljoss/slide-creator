import httpx
import pytest

from app.dependencies import get_http_client


def test_get_http_client_returns_async_client():
    client = get_http_client()
    assert isinstance(client, httpx.AsyncClient)


def test_get_http_client_is_cached():
    assert get_http_client() is get_http_client()


@pytest.mark.asyncio
async def test_gemini_api_accepts_shared_client():
    from app.services.generation.gemini_api import GeminiApiService

    async with httpx.AsyncClient() as shared:
        svc = GeminiApiService(api_key="test-key", http_client=shared)
        assert svc._get_client() is shared


@pytest.mark.asyncio
async def test_cloudflare_image_accepts_shared_client():
    from app.services.media.image_service import CloudflareImageService

    async with httpx.AsyncClient() as shared:
        svc = CloudflareImageService(client=shared)
        assert svc._get_client() is shared


@pytest.mark.asyncio
async def test_stock_photo_accepts_shared_client():
    from app.services.media.image_service import StockPhotoService

    async with httpx.AsyncClient() as shared:
        svc = StockPhotoService(client=shared)
        assert svc._get_client() is shared

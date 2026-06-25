import base64
import logging

import httpx

from app.config import settings

MOCK_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
logger = logging.getLogger(__name__)

class CloudflareImageService:
    def __init__(self):
        self.url = settings.cloudflare_image_worker_url
        self.api_key = settings.cloudflare_image_worker_api_key
        self.model = settings.cloudflare_image_worker_model or "@cf/black-forest-labs/flux-1-schnell"

    async def generate_image(self, prompt: str) -> str | None:
        # Image generation is handled by the Cloudflare worker and is independent
        # of AI_PROVIDER (which only selects the text/content generator, e.g. Gemini).
        # If the worker is not configured, fall back to a mock placeholder so local
        # development and tests do not make network calls.
        if not self.url or not self.api_key:
            return MOCK_PNG_B64 if settings.image_mock_enabled else None

        api_url = self.url.rstrip("/")
        if not api_url.endswith("/v1/images/generations"):
            api_url += "/v1/images/generations"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt,
            "model": self.model,
            "n": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(api_url, json=payload, headers=headers)
                if resp.status_code != 200:
                    logger.warning(
                        "Cloudflare Image Worker returned %s: %s",
                        resp.status_code,
                        resp.text[:300],
                    )
                    return None
                b64 = self._extract_b64(resp.json())
                if b64 is None:
                    logger.warning("Cloudflare Image Worker response had no recognizable image field")
                return b64
        except Exception:
            # Fall back gracefully in case of connection errors or API issues
            logger.warning("Cloudflare Image Worker failed", exc_info=True)
            return None

    @staticmethod
    def _extract_b64(data: object) -> str | None:
        """Pull a base64 image string from common worker response shapes."""
        if not isinstance(data, dict):
            return None
        # OpenAI-compatible: {"data": [{"b64_json": "..."}]}
        items = data.get("data")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            for key in ("b64_json", "image", "b64"):
                value = items[0].get(key)
                if isinstance(value, str) and value:
                    return value
        # Cloudflare native: {"result": {"image": "..."}}
        result = data.get("result")
        if isinstance(result, dict):
            value = result.get("image")
            if isinstance(value, str) and value:
                return value
        # Flat: {"image": "..."}
        value = data.get("image")
        if isinstance(value, str) and value:
            return value
        return None


class StockPhotoService:
    """Key-gated stock-photo lookup (Pexels).

    Returns a base64-encoded JPEG for a short keyword query, or None when no key
    is configured, no photo matches, or any error occurs — so callers can fall
    back to AI image generation.
    """

    SEARCH_URL = "https://api.pexels.com/v1/search"

    def __init__(self):
        self.api_key = settings.stock_photos_api_key
        self.provider = settings.stock_photos_provider

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def search_image(self, query: str) -> str | None:
        if not self.api_key or not query.strip():
            return None
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    self.SEARCH_URL,
                    params={"query": query, "per_page": 1, "orientation": "landscape"},
                    headers={"Authorization": self.api_key},
                )
                if resp.status_code != 200:
                    logger.warning("Stock photo provider returned %s: %s", resp.status_code, resp.text[:200])
                    return None
                img_url = self._extract_image_url(resp.json())
                if not img_url:
                    return None
                img_resp = await client.get(img_url)
                if img_resp.status_code != 200:
                    return None
                return base64.b64encode(img_resp.content).decode("ascii")
        except Exception:
            logger.warning("Stock photo lookup failed", exc_info=True)
            return None

    @staticmethod
    def _extract_image_url(data: object) -> str | None:
        """Pull a landscape image URL from a Pexels search response."""
        if not isinstance(data, dict):
            return None
        photos = data.get("photos")
        if not isinstance(photos, list) or not photos or not isinstance(photos[0], dict):
            return None
        src = photos[0].get("src")
        if not isinstance(src, dict):
            return None
        for key in ("large2x", "large", "landscape", "original"):
            value = src.get(key)
            if isinstance(value, str) and value:
                return value
        return None

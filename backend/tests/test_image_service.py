import logging

from app.services.media.image_service import CloudflareImageService


def test_extract_b64_openai_shape():
    data = {"data": [{"b64_json": "ABC123", "revised_prompt": "x"}]}
    assert CloudflareImageService._extract_b64(data) == "ABC123"


def test_extract_b64_data_image_key():
    data = {"data": [{"image": "IMGDATA"}]}
    assert CloudflareImageService._extract_b64(data) == "IMGDATA"


def test_extract_b64_cloudflare_native_result_shape():
    data = {"result": {"image": "NATIVE64"}}
    assert CloudflareImageService._extract_b64(data) == "NATIVE64"


def test_extract_b64_flat_image_shape():
    assert CloudflareImageService._extract_b64({"image": "FLAT64"}) == "FLAT64"


def test_extract_b64_unrecognized_returns_none():
    assert CloudflareImageService._extract_b64({"foo": "bar"}) is None
    assert CloudflareImageService._extract_b64({"data": []}) is None
    assert CloudflareImageService._extract_b64("not a dict") is None


class _FakeResponse:
    status_code = 200
    text = ""

    @staticmethod
    def json():
        return {"data": [{"b64_json": "REAL_IMAGE_B64"}]}


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return _FakeResponse()


async def test_generate_image_returns_mock_when_worker_not_configured(monkeypatch):
    from app.services.media import image_service as mod

    monkeypatch.setattr(mod.settings, "cloudflare_image_worker_url", "")
    monkeypatch.setattr(mod.settings, "cloudflare_image_worker_api_key", "")
    monkeypatch.setattr(mod.settings, "image_mock_enabled", True)
    svc = mod.CloudflareImageService()
    assert await svc.generate_image("prompt") == mod.MOCK_PNG_B64


async def test_generate_image_returns_none_when_worker_not_configured_and_mock_disabled(monkeypatch):
    from app.services.media import image_service as mod

    monkeypatch.setattr(mod.settings, "cloudflare_image_worker_url", "")
    monkeypatch.setattr(mod.settings, "cloudflare_image_worker_api_key", "")
    monkeypatch.setattr(mod.settings, "image_mock_enabled", False)
    svc = mod.CloudflareImageService()
    assert await svc.generate_image("prompt") is None


async def test_generate_image_uses_cloudflare_even_when_ai_provider_local(monkeypatch):
    """Image generation must be independent of AI_PROVIDER (the content provider)."""
    from app.services.media import image_service as mod

    monkeypatch.setattr(mod.settings, "ai_provider", "local")
    monkeypatch.setattr(mod.settings, "cloudflare_image_worker_url", "https://worker.example/")
    monkeypatch.setattr(mod.settings, "cloudflare_image_worker_api_key", "test-key")

    svc = mod.CloudflareImageService(client=_FakeAsyncClient())
    assert await svc.generate_image("a clean abstract background") == "REAL_IMAGE_B64"


async def test_generate_image_logs_worker_non_200(monkeypatch, caplog):
    from app.services.media import image_service as mod

    class _ErrorResponse:
        status_code = 503
        text = "worker unavailable"

    class _ErrorClient(_FakeAsyncClient):
        async def post(self, *args, **kwargs):
            return _ErrorResponse()

    monkeypatch.setattr(mod.settings, "cloudflare_image_worker_url", "https://worker.example/")
    monkeypatch.setattr(mod.settings, "cloudflare_image_worker_api_key", "test-key")
    monkeypatch.setattr(mod.httpx, "AsyncClient", _ErrorClient)

    svc = mod.CloudflareImageService(client=_ErrorClient())
    with caplog.at_level(logging.WARNING, logger="app.services.media.image_service"):
        result = await svc.generate_image("prompt")

    assert result is None
    assert "Cloudflare Image Worker returned 503" in caplog.text


# --- Stock photo source --------------------------------------------------------

class _FakePexelsResponse:
    status_code = 200
    text = ""

    def __init__(self, payload=None, content=b""):
        self._payload = payload or {}
        self.content = content

    def json(self):
        return self._payload


class _FakeStockClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        if "search" in url:
            return _FakePexelsResponse({"photos": [{"src": {"large": "http://img/large.jpg"}}]})
        return _FakePexelsResponse(content=b"JPEGBYTES")


async def test_stock_disabled_without_key(monkeypatch):
    from app.services.media import image_service as mod

    monkeypatch.setattr(mod.settings, "stock_photos_api_key", "")
    svc = mod.StockPhotoService()
    assert svc.enabled is False
    assert await svc.search_image("banking") is None


async def test_stock_returns_base64_when_configured(monkeypatch):
    import base64

    from app.services.media import image_service as mod

    monkeypatch.setattr(mod.settings, "stock_photos_api_key", "test-key")
    svc = mod.StockPhotoService(client=_FakeStockClient())
    assert svc.enabled is True
    out = await svc.search_image("banking")
    assert out == base64.b64encode(b"JPEGBYTES").decode("ascii")


async def test_stock_logs_provider_non_200(monkeypatch, caplog):
    from app.services.media import image_service as mod

    class _ErrorPexelsResponse(_FakePexelsResponse):
        status_code = 429
        text = "rate limited"

    class _RateLimitedStockClient(_FakeStockClient):
        async def get(self, url, **kwargs):
            return _ErrorPexelsResponse()

    monkeypatch.setattr(mod.settings, "stock_photos_api_key", "test-key")
    monkeypatch.setattr(mod.httpx, "AsyncClient", _RateLimitedStockClient)
    svc = mod.StockPhotoService(client=_RateLimitedStockClient())
    with caplog.at_level(logging.WARNING, logger="app.services.media.image_service"):
        result = await svc.search_image("banking")

    assert result is None
    assert "Stock photo provider returned 429" in caplog.text


async def test_stock_returns_none_on_no_photos(monkeypatch):
    from app.services.media import image_service as mod

    class _NoPhotos(_FakeStockClient):
        async def get(self, url, **kwargs):
            return _FakePexelsResponse({"photos": []})

    monkeypatch.setattr(mod.settings, "stock_photos_api_key", "test-key")
    svc = mod.StockPhotoService(client=_NoPhotos())
    assert await svc.search_image("banking") is None


async def test_resolve_slide_image_prefers_stock_then_falls_back_to_ai(monkeypatch):
    from app.models.schemas import SlideData
    from app.services.media.slide_images import SlideImageResolver

    slide = SlideData(index=2, title="Market", bullets=["x"], notes="", layout="content")

    class _StockOn:
        enabled = True

        async def search_image(self, q):
            return "STOCK64"

    class _StockOff:
        enabled = False

        async def search_image(self, q):
            return None

    class _AI:
        async def generate_image(self, p):
            return "AI64"

    assert await SlideImageResolver(image_service=_AI(), stock_service=_StockOn()).resolve(slide) == "STOCK64"
    assert await SlideImageResolver(image_service=_AI(), stock_service=_StockOff()).resolve(slide) == "AI64"

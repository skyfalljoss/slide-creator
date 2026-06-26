import json
import time
from unittest.mock import MagicMock

import httpx

from app.models.schemas import SlideData
from app.services.platform.session import RedisSessionStore

_NOW = time.time()


def _make_slides(n: int = 2) -> list[SlideData]:
    return [SlideData(index=i, title=f"Slide {i}", bullets=["B"], notes="", layout="content") for i in range(1, n + 1)]


def _fake_response(data: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = {"result": json.dumps(data) if data else None}
    return resp


def test_redis_session_store_create():
    client = MagicMock(spec=httpx.Client)
    store = RedisSessionStore(client=client, prefix="sf:")
    slides = _make_slides()
    session_id = store.create(slides, "sales_9")
    assert session_id is not None
    assert client.post.called


def test_redis_session_store_get():
    client = MagicMock(spec=httpx.Client)
    store = RedisSessionStore(client=client, prefix="sf:")
    slides = _make_slides()
    session_data = {
        "slides": [s.model_dump() for s in slides],
        "created_at": _NOW,
        "deck_type": "sales_9",
        "theme": "minimalist",
        "aspect_ratio": "16:9",
    }
    client.get.return_value = _fake_response(session_data)

    result = store.get("test-session")
    assert result is not None
    assert result["deck_type"] == "sales_9"
    assert len(result["slides"]) == 2


def test_redis_session_store_get_missing():
    client = MagicMock(spec=httpx.Client)
    store = RedisSessionStore(client=client, prefix="sf:")
    client.get.return_value = _fake_response(None)

    result = store.get("missing")
    assert result is None


def test_redis_session_store_update_slide():
    client = MagicMock(spec=httpx.Client)
    store = RedisSessionStore(client=client, prefix="sf:")
    slides = _make_slides(3)
    session_data = {
        "slides": [s.model_dump() for s in slides],
        "created_at": _NOW,
        "deck_type": "sales_9",
        "theme": "minimalist",
        "aspect_ratio": "16:9",
    }
    client.get.return_value = _fake_response(session_data)

    updated = SlideData(index=2, title="Updated", bullets=["B"], notes="", layout="content")
    result = store.update_slide("test-session", updated)
    assert result is True
    assert client.post.called


def test_redis_session_store_update_missing_slide():
    client = MagicMock(spec=httpx.Client)
    store = RedisSessionStore(client=client, prefix="sf:")
    slides = _make_slides(2)
    session_data = {
        "slides": [s.model_dump() for s in slides],
        "created_at": _NOW,
        "deck_type": "sales_9",
        "theme": "minimalist",
        "aspect_ratio": "16:9",
    }
    client.get.return_value = _fake_response(session_data)

    updated = SlideData(index=99, title="Missing", bullets=["B"], notes="", layout="content")
    result = store.update_slide("test-session", updated)
    assert result is False


def test_redis_session_store_get_expired():
    client = MagicMock(spec=httpx.Client)
    store = RedisSessionStore(client=client, prefix="sf:", ttl=1)
    slides = _make_slides()
    session_data = {
        "slides": [s.model_dump() for s in slides],
        "created_at": 100.0,
        "deck_type": "sales_9",
        "theme": "minimalist",
        "aspect_ratio": "16:9",
    }
    client.get.return_value = _fake_response(session_data)

    result = store.get("test-session", ttl_seconds=0)
    assert result is None


import json
import uuid
import time
from typing import Protocol, TypedDict

import httpx

from app.config import settings
from app.models.schemas import SlideData


class SessionData(TypedDict):
    slides: list[SlideData]
    created_at: float
    deck_type: str
    theme: str
    aspect_ratio: str


class SessionStore(Protocol):
    def create(self, slides: list[SlideData], deck_type: str, theme: str = "minimalist", aspect_ratio: str = "16:9") -> str: ...
    def get(self, session_id: str, ttl_seconds: int | None = None) -> SessionData | None: ...
    def update_slide(self, session_id: str, slide: SlideData, ttl_seconds: int | None = None) -> bool: ...
    def purge_expired(self, ttl_seconds: int | None = None) -> int: ...


class LocalSessionStore:
    def __init__(self) -> None:
        self._store: dict[str, SessionData] = {}

    def create(self, slides: list[SlideData], deck_type: str, theme: str = "minimalist", aspect_ratio: str = "16:9") -> str:
        session_id = str(uuid.uuid4())
        self._store[session_id] = {
            "slides": slides,
            "created_at": time.time(),
            "deck_type": deck_type,
            "theme": theme,
            "aspect_ratio": aspect_ratio,
        }
        return session_id

    def _default_ttl_seconds(self) -> int:
        return settings.session_ttl_minutes * 60

    def get(self, session_id: str, ttl_seconds: int | None = None) -> SessionData | None:
        ttl_seconds = self._default_ttl_seconds() if ttl_seconds is None else ttl_seconds
        data = self._store.get(session_id)
        if data is None:
            return None
        if time.time() - data["created_at"] > ttl_seconds:
            del self._store[session_id]
            return None
        return data

    def update_slide(self, session_id: str, slide: SlideData, ttl_seconds: int | None = None) -> bool:
        data = self.get(session_id, ttl_seconds=ttl_seconds)
        if data is None:
            return False
        for i, s in enumerate(data["slides"]):
            if s.index == slide.index:
                data["slides"][i] = slide
                return True
        return False

    def purge_expired(self, ttl_seconds: int | None = None) -> int:
        ttl_seconds = self._default_ttl_seconds() if ttl_seconds is None else ttl_seconds
        now = time.time()
        expired = [sid for sid, data in self._store.items() if now - data["created_at"] > ttl_seconds]
        for sid in expired:
            del self._store[sid]
        return len(expired)


class RedisSessionStore:
    def __init__(self, client: httpx.Client, prefix: str = "sf:session:", ttl: int | None = None):
        self._client = client
        self._prefix = prefix
        self._ttl = ttl or settings.session_ttl_minutes * 60

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def create(self, slides: list[SlideData], deck_type: str, theme: str = "minimalist", aspect_ratio: str = "16:9") -> str:
        session_id = str(uuid.uuid4())
        data: SessionData = {
            "slides": slides,
            "created_at": time.time(),
            "deck_type": deck_type,
            "theme": theme,
            "aspect_ratio": aspect_ratio,
        }
        raw = json.dumps(data, default=str)
        self._client.post(f"/set/{self._key(session_id)}", content=raw)
        return session_id

    def get(self, session_id: str, ttl_seconds: int | None = None) -> SessionData | None:
        resp = self._client.get(f"/get/{self._key(session_id)}")
        payload = resp.json()
        raw = payload.get("result")
        if raw is None:
            return None
        data: dict = json.loads(raw)
        created_at = data["created_at"]
        ttl = self._ttl if ttl_seconds is None else ttl_seconds
        if time.time() - created_at > ttl:
            self._client.post(f"/del/{self._key(session_id)}")
            return None
        slides = [SlideData(**s) if isinstance(s, dict) else s for s in data["slides"]]
        return SessionData(
            slides=slides,
            created_at=created_at,
            deck_type=data["deck_type"],
            theme=data.get("theme", "minimalist"),
            aspect_ratio=data.get("aspect_ratio", "16:9"),
        )

    def update_slide(self, session_id: str, slide: SlideData, ttl_seconds: int | None = None) -> bool:
        data = self.get(session_id, ttl_seconds=ttl_seconds)
        if data is None:
            return False
        for i, s in enumerate(data["slides"]):
            if s.index == slide.index:
                data["slides"][i] = slide
                raw = json.dumps(
                    {
                        "slides": [s.model_dump() for s in data["slides"]],
                        "created_at": data["created_at"],
                        "deck_type": data["deck_type"],
                        "theme": data["theme"],
                        "aspect_ratio": data["aspect_ratio"],
                    },
                    default=str,
                )
                self._client.post(f"/set/{self._key(session_id)}", content=raw)
                return True
        return False

    def purge_expired(self, ttl_seconds: int | None = None) -> int:
        return 0


_default_store = LocalSessionStore()


def create_session(slides: list[SlideData], deck_type: str, theme: str = "minimalist", aspect_ratio: str = "16:9") -> str:
    return _default_store.create(slides, deck_type, theme, aspect_ratio)


def get_session(session_id: str, ttl_seconds: int | None = None) -> SessionData | None:
    return _default_store.get(session_id, ttl_seconds)


def update_slide(session_id: str, slide: SlideData, ttl_seconds: int | None = None) -> bool:
    return _default_store.update_slide(session_id, slide, ttl_seconds)


def purge_expired(ttl_seconds: int | None = None) -> int:
    return _default_store.purge_expired(ttl_seconds)

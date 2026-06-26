import uuid
import time
from typing import Protocol, TypedDict

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


_default_store = LocalSessionStore()


def create_session(slides: list[SlideData], deck_type: str, theme: str = "minimalist", aspect_ratio: str = "16:9") -> str:
    return _default_store.create(slides, deck_type, theme, aspect_ratio)


def get_session(session_id: str, ttl_seconds: int | None = None) -> SessionData | None:
    return _default_store.get(session_id, ttl_seconds)


def update_slide(session_id: str, slide: SlideData, ttl_seconds: int | None = None) -> bool:
    return _default_store.update_slide(session_id, slide, ttl_seconds)


def purge_expired(ttl_seconds: int | None = None) -> int:
    return _default_store.purge_expired(ttl_seconds)

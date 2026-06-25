import uuid
import time
from typing import TypedDict

from app.config import settings
from app.models.schemas import SlideData


class SessionData(TypedDict):
    slides: list[SlideData]
    created_at: float
    deck_type: str
    theme: str
    aspect_ratio: str


_store: dict[str, SessionData] = {}


def create_session(slides: list[SlideData], deck_type: str, theme: str = "minimalist", aspect_ratio: str = "16:9") -> str:
    session_id = str(uuid.uuid4())
    _store[session_id] = {
        "slides": slides,
        "created_at": time.time(),
        "deck_type": deck_type,
        "theme": theme,
        "aspect_ratio": aspect_ratio,
    }
    return session_id


def _default_ttl_seconds() -> int:
    return settings.session_ttl_minutes * 60


def get_session(session_id: str, ttl_seconds: int | None = None) -> SessionData | None:
    ttl_seconds = _default_ttl_seconds() if ttl_seconds is None else ttl_seconds
    data = _store.get(session_id)
    if data is None:
        return None
    if time.time() - data["created_at"] > ttl_seconds:
        del _store[session_id]
        return None
    return data


def update_slide(session_id: str, slide: SlideData, ttl_seconds: int | None = None) -> bool:
    data = get_session(session_id, ttl_seconds=ttl_seconds)
    if data is None:
        return False
    for i, s in enumerate(data["slides"]):
        if s.index == slide.index:
            data["slides"][i] = slide
            return True
    return False


def purge_expired(ttl_seconds: int | None = None) -> int:
    ttl_seconds = _default_ttl_seconds() if ttl_seconds is None else ttl_seconds
    now = time.time()
    expired = [sid for sid, data in _store.items() if now - data["created_at"] > ttl_seconds]
    for sid in expired:
        del _store[sid]
    return len(expired)

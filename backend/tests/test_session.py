import time

from app.services.session import create_session, get_session, update_slide, purge_expired
from app.models.schemas import SlideData


def _make_slides(n: int = 3) -> list[SlideData]:
    return [SlideData(index=i, title=f"Slide {i}", bullets=["Bullet 1"], notes="", layout="content") for i in range(1, n + 1)]


def test_create_and_get_session():
    slides = _make_slides()
    sid = create_session(slides, "sales_9")
    data = get_session(sid)
    assert data is not None
    assert data["deck_type"] == "sales_9"
    assert len(data["slides"]) == 3


def test_get_nonexistent_session():
    assert get_session("does-not-exist") is None


def test_update_slide():
    slides = _make_slides()
    sid = create_session(slides, "internal_6")

    updated = SlideData(index=2, title="Updated Slide 2", bullets=["New bullet"], notes="", layout="content")
    result = update_slide(sid, updated)
    assert result is True

    data = get_session(sid)
    slide2 = [s for s in data["slides"] if s.index == 2][0]
    assert slide2.title == "Updated Slide 2"


def test_update_nonexistent_slide():
    slides = _make_slides()
    sid = create_session(slides, "sales_9")

    updated = SlideData(index=99, title="Ghost", bullets=[], notes="", layout="content")
    result = update_slide(sid, updated)
    assert result is False


def test_purge_expired():
    slides = _make_slides()
    create_session(slides, "sales_9")
    count = purge_expired(ttl_seconds=0)
    assert count >= 1


def test_get_session_enforces_ttl():
    slides = _make_slides()
    sid = create_session(slides, "sales_9")
    data = get_session(sid)
    assert data is not None
    data["created_at"] = time.time() - 2

    assert get_session(sid, ttl_seconds=1) is None


def test_get_session_defaults_to_configured_ttl(monkeypatch):
    monkeypatch.setattr("app.services.session.settings.session_ttl_minutes", 1)
    slides = _make_slides()
    sid = create_session(slides, "sales_9")
    data = get_session(sid)
    assert data is not None
    data["created_at"] = time.time() - 61

    assert get_session(sid) is None


def test_update_slide_rejects_expired_session():
    slides = _make_slides()
    sid = create_session(slides, "sales_9")
    data = get_session(sid)
    assert data is not None
    data["created_at"] = time.time() - 2

    updated = SlideData(index=1, title="Updated", bullets=[], notes="", layout="content")

    assert update_slide(sid, updated, ttl_seconds=1) is False

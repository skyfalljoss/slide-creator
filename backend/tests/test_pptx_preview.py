import base64

import pytest

from app.models.schemas import SlideData, SlidePreviewResponse
from app.services.presentation.pptx_preview import PptxPreviewService


PNG_BYTES = b"\x89PNG\r\n\x1a\npreview"


def test_slide_preview_response_contains_png_metadata():
    payload = SlidePreviewResponse(
        deck_id="deck-1",
        slide_index=2,
        image_b64=base64.b64encode(PNG_BYTES).decode("ascii"),
        width=1920,
        height=1080,
        updated_at="2026-06-26T00:00:00Z",
    )

    assert payload.deck_id == "deck-1"
    assert payload.slide_index == 2
    assert base64.b64decode(payload.image_b64) == PNG_BYTES
    assert payload.width == 1920
    assert payload.height == 1080


def test_preview_service_renders_selected_slide_only(monkeypatch: pytest.MonkeyPatch, tmp_path):
    captured: dict[str, object] = {}
    service = PptxPreviewService(cache_dir=tmp_path, soffice_path="soffice")

    def fake_find_soffice():
        return "/usr/bin/soffice"

    def fake_render(slide: SlideData, *, theme: str, aspect_ratio: str) -> bytes:
        captured["slide_index"] = slide.index
        captured["slide_title"] = slide.title
        captured["theme"] = theme
        captured["aspect_ratio"] = aspect_ratio
        return b"PK-pptx"

    def fake_convert(pptx_bytes: bytes, *, soffice: str) -> bytes:
        captured["pptx_bytes"] = pptx_bytes
        captured["soffice"] = soffice
        return PNG_BYTES

    monkeypatch.setattr(service, "_find_soffice", fake_find_soffice)
    monkeypatch.setattr(service, "_render_single_slide_pptx", fake_render)
    monkeypatch.setattr(service, "_convert_pptx_to_png", fake_convert)

    slides = [
        SlideData(index=1, title="Cover", bullets=[], notes="", layout="title"),
        SlideData(index=2, title="Today's Discussion", bullets=["One"], notes="", layout="content"),
    ]

    preview = service.render_deck_slide(
        deck_id="deck-1",
        slides=slides,
        deck_type="sales_9",
        theme="minimalist",
        aspect_ratio="16:9",
        slide_index=2,
        updated_at="2026-06-26T00:00:00Z",
    )

    assert captured == {
        "slide_index": 2,
        "slide_title": "Presentation Agenda",
        "theme": "minimalist",
        "aspect_ratio": "16:9",
        "pptx_bytes": b"PK-pptx",
        "soffice": "/usr/bin/soffice",
    }
    assert preview.deck_id == "deck-1"
    assert preview.slide_index == 2
    assert base64.b64decode(preview.image_b64) == PNG_BYTES


def test_preview_service_falls_back_when_soffice_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path):
    service = PptxPreviewService(cache_dir=tmp_path, soffice_path="missing-soffice")
    monkeypatch.setattr(service, "_find_soffice", lambda: None)

    slides = [
        SlideData(index=1, title="Cover", bullets=[], notes="", layout="title"),
        SlideData(index=2, title="Presentation Agenda", bullets=["Market Opportunity"], notes="", layout="content"),
    ]

    preview = service.render_deck_slide(
        deck_id="deck-1",
        slides=slides,
        deck_type="sales_9",
        theme="minimalist",
        aspect_ratio="16:9",
        slide_index=2,
    )

    assert base64.b64decode(preview.image_b64).startswith(b"\x89PNG")
    assert preview.width == 1920
    assert preview.height == 1080


def test_preview_service_rejects_invalid_slide_index(tmp_path):
    service = PptxPreviewService(cache_dir=tmp_path, soffice_path="soffice")
    slides = [SlideData(index=1, title="Cover", bullets=[], notes="", layout="title")]

    with pytest.raises(IndexError, match="Slide index 99 is not available"):
        service.render_deck_slide(
            deck_id="deck-1",
            slides=slides,
            deck_type="sales_9",
            theme="minimalist",
            aspect_ratio="16:9",
            slide_index=99,
        )

from app.models.schemas import SlideData
from app.services.generation.deck_normalizer import normalize_deck


def _slide(index: int, title: str, *, variant: str | None = None) -> SlideData:
    return SlideData(
        index=index,
        title=title,
        bullets=["Point"],
        notes="",
        layout="content",
        variant=variant,
    )


def test_normalize_deck_appends_thank_you_when_room_available():
    slides = [_slide(10, "Cover"), _slide(20, "Plan")]

    normalized = normalize_deck(slides, max_count=6)

    assert [slide.index for slide in normalized] == [1, 2, 3]
    assert normalized[-1].title == "Thank You"
    assert normalized[-1].subtitle == "Questions and open discussion."
    assert normalized[-1].layout == "content"
    assert normalized[-1].variant == "closing"
    assert normalized[-1].bullets == []


def test_normalize_deck_converts_last_slide_to_thank_you_at_max_count():
    slides = [_slide(i, f"Slide {i}") for i in range(1, 13)]

    normalized = normalize_deck(slides, max_count=12)

    assert len(normalized) == 12
    assert normalized[-1].title == "Thank You"
    assert normalized[-1].variant == "closing"
    assert normalized[-1].subtitle == "Questions and open discussion."


def test_normalize_deck_repairs_existing_thank_you_slide():
    slides = [_slide(1, "Cover"), _slide(2, "Thanks", variant="three_points")]
    slides[-1].subtitle = None
    slides[-1].bullets = ["Too much closing content"]
    slides[-1].layout = "next_steps"

    normalized = normalize_deck(slides, max_count=9)

    assert normalized[-1].title == "Thank You"
    assert normalized[-1].subtitle == "Questions and open discussion."
    assert normalized[-1].layout == "content"
    assert normalized[-1].variant == "closing"
    assert normalized[-1].bullets == []

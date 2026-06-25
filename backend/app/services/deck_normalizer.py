from app.models.schemas import SlideData


THANK_YOU_TITLE = "Thank You"
THANK_YOU_SUBTITLE = "Questions and open discussion."


def normalize_deck(slides: list[SlideData], *, max_count: int | None = None) -> list[SlideData]:
    """Return a presentation-ready slide list with stable indexes and ending."""
    normalized = [slide.model_copy(deep=True) for slide in slides]
    for index, slide in enumerate(normalized, 1):
        slide.index = index

    if normalized and _is_thank_you(normalized[-1]):
        _normalize_thank_you(normalized[-1])
        return normalized

    if max_count is not None and len(normalized) >= max_count:
        if not normalized:
            return normalized
        _normalize_thank_you(normalized[-1])
        return normalized

    normalized.append(
        SlideData(
            index=len(normalized) + 1,
            title=THANK_YOU_TITLE,
            subtitle=THANK_YOU_SUBTITLE,
            bullets=[],
            notes="",
            layout="content",
            variant="closing",
        )
    )
    return normalized


def _is_thank_you(slide: SlideData) -> bool:
    return slide.title.strip().lower().rstrip(".!") in {"thank you", "thanks"}


def _normalize_thank_you(slide: SlideData) -> None:
    slide.title = THANK_YOU_TITLE
    slide.subtitle = slide.subtitle or THANK_YOU_SUBTITLE
    slide.bullets = []
    slide.notes = slide.notes or ""
    slide.layout = "content"
    slide.variant = "closing"
    slide.blocks = None
    slide.chart_data = None
    slide.chart_recommendation = None
    slide.chart_audit = None

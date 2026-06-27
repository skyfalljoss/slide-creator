from app.models.schemas import SlideData


THANK_YOU_TITLE = "Thank You"
THANK_YOU_SUBTITLE = "Questions and open discussion."
AGENDA_TITLE = "Presentation Agenda"
MAX_CHAPTERS = 4
STRUCTURAL_AGENDA_TITLES = frozenset(
    {
        "agenda",
        "presentation agenda",
        "outline",
        "presentation outline",
        "overview",
        "presentation overview",
        "roadmap",
        "strategic roadmap",
        "today's discussion",
    }
)
AGENDA_DESCRIPTION_FALLBACK = "Key context, evidence, and decisions for this chapter."


def normalize_deck(slides: list[SlideData], *, max_count: int | None = None) -> list[SlideData]:
    """Return a presentation-ready slide list with stable indexes and ending."""
    normalized = [slide.model_copy(deep=True) for slide in slides]
    for index, slide in enumerate(normalized, 1):
        slide.index = index

    agenda = _ensure_agenda(normalized, max_count=max_count)

    if normalized and _is_thank_you(normalized[-1]):
        _normalize_thank_you(normalized[-1])
    elif max_count is not None and len(normalized) >= max_count:
        if not normalized:
            return normalized
        _normalize_thank_you(normalized[-1])
    else:
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

    if agenda is not None and agenda in normalized:
        _normalize_agenda(agenda, normalized)
    _clear_noncontent_chapters(normalized, agenda)
    _avoid_adjacent_variant_repeats(normalized)
    _refresh_indexes(normalized)
    return normalized


def _ensure_agenda(slides: list[SlideData], *, max_count: int | None) -> SlideData | None:
    if not slides:
        return None
    if max_count is not None and max_count < 3:
        return None

    navigation_candidates = [
        slide for slide in slides[1:] if _is_overview_title(slide.title)
    ]
    agenda = navigation_candidates[0] if navigation_candidates else None
    if agenda is not None:
        duplicate_ids = {id(slide) for slide in navigation_candidates[1:]}
        slides[:] = [
            slide for slide in slides if id(slide) not in duplicate_ids
        ]
        slides.remove(agenda)
        slides.insert(1, agenda)
        return agenda

    if max_count is not None and len(slides) >= max_count:
        if len(slides) == 1:
            return None
        removal_index = -2 if _is_thank_you(slides[-1]) and len(slides) > 2 else -1
        del slides[removal_index]

    agenda = _build_agenda()
    slides.insert(1, agenda)
    return agenda


def _build_agenda() -> SlideData:
    return SlideData(
        index=2,
        title=AGENDA_TITLE,
        bullets=[],
        notes="Introduce the flow of the presentation.",
        layout="content",
        variant="process",
        visual_direction="Presentation agenda slide with four numbered cards.",
    )


def _normalize_agenda(agenda: SlideData, slides: list[SlideData]) -> None:
    chapter_definitions = _assign_chapters(slides, agenda)
    agenda.title = AGENDA_TITLE
    agenda.kicker = None
    agenda.subtitle = None
    agenda.chapter_number = None
    agenda.chapter_title = None
    agenda.bullets = [title for _, title, _ in chapter_definitions]
    agenda.notes = agenda.notes or "Introduce the flow of the presentation."
    agenda.layout = "content"
    agenda.variant = "process"
    agenda.blocks = [
        {
            "type": "process",
            "steps": [
                {"title": title, "body": description}
                for _, title, description in chapter_definitions
            ],
        }
    ]
    agenda.chart_data = None
    agenda.chart_recommendation = None
    agenda.chart_audit = None
    agenda.visual_direction = "Presentation agenda slide with four numbered cards."


def _assign_chapters(
    slides: list[SlideData], agenda: SlideData
) -> list[tuple[int, str, str]]:
    content_slides = _content_for_chapters(slides, agenda)
    if not content_slides:
        return []

    generated_numbers = [
        slide.chapter_number for slide in content_slides if slide.chapter_number is not None
    ]
    unique_numbers = sorted(set(generated_numbers))
    dense_numbers = bool(unique_numbers) and unique_numbers == list(
        range(1, unique_numbers[-1] + 1)
    )
    use_generated = (
        content_slides[0].chapter_number is not None
        and generated_numbers == sorted(generated_numbers)
        and dense_numbers
    )

    if use_generated:
        current_number = generated_numbers[0]
        for slide in content_slides:
            if slide.chapter_number is not None:
                current_number = slide.chapter_number
            else:
                slide.chapter_number = current_number
    else:
        chapter_count = min(MAX_CHAPTERS, len(content_slides))
        for position, slide in enumerate(content_slides):
            slide.chapter_number = _fallback_chapter_number(
                position, len(content_slides), chapter_count
            )

    chapter_titles: dict[int, str] = {}
    chapter_first_slides: dict[int, SlideData] = {}
    for slide in content_slides:
        chapter_number = slide.chapter_number
        if chapter_number is None:
            continue
        chapter_first_slides.setdefault(chapter_number, slide)
        generated_title = (
            _concise(slide.chapter_title or "", max_words=5, max_chars=42)
            if use_generated
            else ""
        )
        if generated_title and chapter_number not in chapter_titles:
            chapter_titles[chapter_number] = generated_title

    for chapter_number, first_slide in chapter_first_slides.items():
        fallback_title = _concise(first_slide.title, max_words=5, max_chars=42)
        chapter_titles.setdefault(
            chapter_number, fallback_title or f"Chapter {chapter_number}"
        )

    for slide in content_slides:
        chapter_number = slide.chapter_number
        if chapter_number is None:
            continue
        slide.chapter_title = chapter_titles[chapter_number]

    return [
        (number, chapter_titles[number], _agenda_description(chapter_first_slides[number]))
        for number in sorted(chapter_titles)
    ]


def _content_for_chapters(slides: list[SlideData], agenda: SlideData) -> list[SlideData]:
    return [
        slide
        for index, slide in enumerate(slides)
        if index > 0
        and slide is not agenda
        and slide.layout != "title"
        and slide.variant != "closing"
        and not _is_thank_you(slide)
    ]


def _fallback_chapter_number(position: int, slide_count: int, chapter_count: int) -> int:
    base_size, larger_chapters = divmod(slide_count, chapter_count)
    cursor = 0
    for chapter_number in range(1, chapter_count + 1):
        cursor += base_size + (1 if chapter_number <= larger_chapters else 0)
        if position < cursor:
            return chapter_number
    return chapter_count


def _agenda_description(slide: SlideData) -> str:
    source = slide.callout or slide.subtitle or next(
        (bullet for bullet in slide.bullets if bullet.strip()), ""
    )
    concise = _concise(source or AGENDA_DESCRIPTION_FALLBACK, max_words=14, max_chars=90)
    return concise or AGENDA_DESCRIPTION_FALLBACK


def _concise(text: str, *, max_words: int, max_chars: int) -> str:
    words = text.split()
    selected: list[str] = []
    for word in words[:max_words]:
        candidate = " ".join([*selected, word])
        if len(candidate) > max_chars:
            break
        selected.append(word)
    return " ".join(selected)


def _clear_noncontent_chapters(slides: list[SlideData], agenda: SlideData | None) -> None:
    for index, slide in enumerate(slides):
        if (
            index == 0
            or slide is agenda
            or slide.layout == "title"
            or slide.variant == "closing"
            or _is_thank_you(slide)
        ):
            slide.chapter_number = None
            slide.chapter_title = None


def _is_overview_title(title: str) -> bool:
    normalized = " ".join(title.strip().lower().split())
    return normalized in STRUCTURAL_AGENDA_TITLES or normalized.startswith(
        "strategic roadmap for "
    )


def _is_thank_you_title(title: str) -> bool:
    return title.strip().lower().rstrip(".!") in {"thank you", "thanks"}


def _avoid_adjacent_variant_repeats(slides: list[SlideData]) -> None:
    previous: str | None = None
    for slide in slides:
        variant = slide.variant
        if variant and variant == previous and variant not in {"cover", "closing"}:
            slide.variant = _alternate_variant(variant)
            if slide.variant in {"three_points", "big_statement", "split_image"}:
                slide.blocks = None
        previous = slide.variant


def _alternate_variant(variant: str) -> str:
    return {
        "process": "three_points",
        "three_points": "big_statement",
        "big_statement": "split_image",
        "split_image": "three_points",
        "big_stat": "comparison_table",
        "comparison_table": "three_points",
        "before_after": "comparison_table",
        "quote": "big_statement",
    }.get(variant, "three_points")


def _refresh_indexes(slides: list[SlideData]) -> None:
    for index, slide in enumerate(slides, 1):
        slide.index = index


def _is_thank_you(slide: SlideData) -> bool:
    return _is_thank_you_title(slide.title)


def _normalize_thank_you(slide: SlideData) -> None:
    slide.title = THANK_YOU_TITLE
    slide.subtitle = slide.subtitle or THANK_YOU_SUBTITLE
    slide.bullets = []
    slide.notes = slide.notes or ""
    slide.layout = "content"
    slide.variant = "closing"
    slide.chapter_number = None
    slide.chapter_title = None
    slide.blocks = None
    slide.chart_data = None
    slide.chart_recommendation = None
    slide.chart_audit = None

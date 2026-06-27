import pytest

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

    assert [slide.index for slide in normalized] == [1, 2, 3, 4]
    assert normalized[1].title == "Presentation Agenda"
    assert normalized[1].layout == "content"
    assert normalized[1].variant == "process"
    assert normalized[1].bullets == ["Plan"]
    assert normalized[-1].title == "Thank You"
    assert normalized[-1].subtitle == "Questions and open discussion."
    assert normalized[-1].layout == "content"
    assert normalized[-1].variant == "closing"
    assert normalized[-1].bullets == []


def test_normalize_deck_converts_last_slide_to_thank_you_at_max_count():
    slides = [_slide(i, f"Slide {i}") for i in range(1, 13)]

    normalized = normalize_deck(slides, max_count=12)

    assert len(normalized) == 12
    assert normalized[1].title == "Presentation Agenda"
    assert normalized[-1].title == "Thank You"
    assert normalized[-1].variant == "closing"
    assert normalized[-1].subtitle == "Questions and open discussion."


def test_normalize_deck_preserves_empty_deck_at_zero_max_count():
    assert normalize_deck([], max_count=0) == []


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


def test_normalize_deck_does_not_duplicate_existing_outline():
    slides = [_slide(1, "Cover"), _slide(2, "Presentation Outline"), _slide(3, "Plan")]
    slides[1].variant = "process"

    normalized = normalize_deck(slides, max_count=6)

    assert [slide.title for slide in normalized].count("Presentation Agenda") == 1
    assert normalized[1].title == "Presentation Agenda"


def test_normalize_deck_reuses_existing_roadmap_as_single_overview():
    slides = [
        _slide(1, "Cover"),
        _slide(2, "Strategic Roadmap for Growth", variant="process"),
        _slide(3, "Market Opportunity", variant="process"),
        _slide(4, "Solution", variant="process"),
        _slide(5, "Traction", variant="big_statement"),
    ]
    slides[1].bullets = ["Market Opportunity", "Solution", "Traction"]

    normalized = normalize_deck(slides, max_count=8)

    assert [slide.title for slide in normalized].count("Presentation Agenda") == 1
    assert all("Roadmap" not in slide.title for slide in normalized)
    assert normalized[1].bullets[:3] == ["Market Opportunity", "Solution", "Traction"]
    assert normalized[2].variant != normalized[3].variant


def test_normalize_deck_builds_professional_agenda_with_repeated_chapters():
    slides = [
        _slide(1, "Cover", variant="cover"),
        _slide(2, "Market Size", variant="big_statement"),
        _slide(3, "Customer Demand", variant="three_points"),
        _slide(4, "Platform", variant="split_image"),
        _slide(5, "Technology", variant="three_points"),
        _slide(6, "Traction", variant="big_stat"),
        _slide(7, "Funding", variant="comparison_table"),
    ]

    normalized = normalize_deck(slides, max_count=10)

    assert normalized[1].title == "Presentation Agenda"
    content = normalized[2:-1]
    assert [slide.chapter_number for slide in content] == [1, 1, 2, 2, 3, 4]
    assert [slide.chapter_title for slide in content] == [
        "Market Size",
        "Market Size",
        "Platform",
        "Platform",
        "Traction",
        "Funding",
    ]
    assert normalized[0].chapter_number is None
    assert normalized[1].chapter_number is None
    assert normalized[-1].chapter_number is None


def test_normalize_agenda_uses_concise_source_copy_without_generic_sentence():
    slides = [
        _slide(1, "Cover", variant="cover"),
        _slide(2, "Market Opportunity"),
        _slide(3, "Customer Demand"),
        _slide(4, "Platform"),
        _slide(5, "Traction"),
    ]
    slides[1].callout = (
        "Short-video demand is expanding as creators seek faster production workflows "
        "across major platforms without sacrificing quality or control."
    )
    slides[2].subtitle = "Teams need scalable tools that reduce production time and operating costs."
    slides[3].bullets = ["Automation turns complex editing workflows into repeatable publishing operations."]
    slides[4].bullets = []

    normalized = normalize_deck(slides, max_count=8)
    steps = normalized[1].blocks[0]["steps"]

    assert [step["body"] for step in steps] == [
        "Short-video demand is expanding as creators seek faster production workflows across major",
        "Teams need scalable tools that reduce production time and operating costs.",
        "Automation turns complex editing workflows into repeatable publishing operations.",
        "Key context, evidence, and decisions for this chapter.",
    ]
    assert all(step["body"] != "The context and core insight for the discussion." for step in steps)
    assert all(len(step["body"].split()) <= 14 for step in steps)
    assert all(len(step["body"]) <= 90 for step in steps)


def test_normalize_deck_preserves_generated_chapters_and_orders_agenda_titles():
    slides = [
        _slide(1, "Cover", variant="cover"),
        _slide(2, "Market Size"),
        _slide(3, "Customer Demand"),
        _slide(4, "Platform"),
        _slide(5, "Traction"),
    ]
    slides[1].chapter_number = 1
    slides[1].chapter_title = "Market Opportunity"
    slides[2].chapter_number = 1
    slides[2].chapter_title = "Stale Alternate Title"
    slides[3].chapter_number = 2
    slides[3].chapter_title = "Solution and Traction"
    slides[4].chapter_number = 2
    slides[4].chapter_title = "Solution and Traction"

    normalized = normalize_deck(slides, max_count=8)
    content = normalized[2:-1]

    assert [slide.chapter_number for slide in content] == [1, 1, 2, 2]
    assert [slide.chapter_title for slide in content] == [
        "Market Opportunity",
        "Market Opportunity",
        "Solution and Traction",
        "Solution and Traction",
    ]
    assert normalized[1].bullets == ["Market Opportunity", "Solution and Traction"]


def test_normalize_deck_reuses_one_overview_and_removes_overview_duplicates():
    slides = [
        _slide(1, "Cover", variant="cover"),
        _slide(2, "Presentation Outline", variant="process"),
        _slide(3, "Strategic Roadmap", variant="process"),
        _slide(4, "Market Opportunity", variant="big_statement"),
        _slide(5, "Solution", variant="three_points"),
    ]
    slides[1].bullets = ["Stale agenda item"]

    normalized = normalize_deck(slides, max_count=8)
    overview_like = [
        slide
        for slide in normalized
        if any(
            word in slide.title.lower()
            for word in ("agenda", "outline", "overview", "roadmap", "discussion")
        )
    ]

    assert [slide.title for slide in overview_like] == ["Presentation Agenda"]
    assert normalized[1].bullets == ["Market Opportunity", "Solution"]


def test_normalize_deck_reuses_late_overview_and_removes_all_later_duplicates():
    slides = [
        _slide(1, "Cover", variant="cover"),
        _slide(2, "Market Opportunity", variant="big_statement"),
        _slide(3, "Customer Demand", variant="three_points"),
        _slide(4, "Platform", variant="split_image"),
        _slide(5, "Presentation Overview", variant="process"),
        _slide(6, "Tail Analysis", variant="big_stat"),
        _slide(7, "Strategic Roadmap", variant="process"),
    ]

    normalized = normalize_deck(slides, max_count=9)

    assert [slide.title for slide in normalized] == [
        "Cover",
        "Presentation Agenda",
        "Market Opportunity",
        "Customer Demand",
        "Platform",
        "Tail Analysis",
        "Thank You",
    ]
    assert [slide.index for slide in normalized] == list(range(1, 8))


def test_normalize_deck_uses_fallback_when_first_content_lacks_chapter_number():
    slides = [
        _slide(1, "Cover", variant="cover"),
        _slide(2, "Market Size"),
        _slide(3, "Customer Demand"),
        _slide(4, "Platform"),
        _slide(5, "Technology"),
        _slide(6, "Traction"),
        _slide(7, "Funding"),
    ]
    for slide, chapter_number in zip(slides[2:], [2, 2, 3, 3, 4], strict=True):
        slide.chapter_number = chapter_number
        slide.chapter_title = f"Generated Chapter {chapter_number}"

    normalized = normalize_deck(slides, max_count=10)

    assert [slide.chapter_number for slide in normalized[2:-1]] == [1, 1, 2, 2, 3, 4]
    assert normalized[2].chapter_title == "Market Size"


def test_normalize_deck_uses_first_generated_title_anywhere_in_each_chapter():
    slides = [
        _slide(1, "Cover", variant="cover"),
        _slide(2, "Market Size"),
        _slide(3, "Customer Demand"),
        _slide(4, "Platform"),
        _slide(5, "Traction"),
    ]
    for slide, chapter_number in zip(slides[1:], [1, 1, 2, 2], strict=True):
        slide.chapter_number = chapter_number
    slides[2].chapter_title = "Market Opportunity"
    slides[4].chapter_title = "Solution and Traction"

    normalized = normalize_deck(slides, max_count=8)

    assert [slide.chapter_title for slide in normalized[2:-1]] == [
        "Market Opportunity",
        "Market Opportunity",
        "Solution and Traction",
        "Solution and Traction",
    ]
    assert normalized[1].bullets == ["Market Opportunity", "Solution and Traction"]


def test_normalize_deck_adds_empty_agenda_to_cover_only_deck_when_room_allows():
    normalized = normalize_deck([_slide(1, "Cover", variant="cover")], max_count=3)

    assert [slide.title for slide in normalized] == [
        "Cover",
        "Presentation Agenda",
        "Thank You",
    ]
    assert normalized[1].bullets == []
    assert normalized[1].blocks == [{"type": "process", "steps": []}]


@pytest.mark.parametrize(
    "title",
    [
        "Agenda",
        "Presentation Agenda",
        "Outline",
        "Presentation Outline",
        "Overview",
        "Presentation Overview",
        "Roadmap",
        "Strategic Roadmap",
        "Strategic Roadmap for Growth",
        "Today's Discussion",
    ],
)
def test_normalize_deck_recognizes_structural_overview_titles(title: str):
    slides = [
        _slide(1, "Cover", variant="cover"),
        _slide(2, "Market Opportunity"),
        _slide(3, title, variant="process"),
        _slide(4, "Tail Analysis"),
    ]

    normalized = normalize_deck(slides, max_count=7)

    assert normalized[1].title == "Presentation Agenda"
    assert title not in [slide.title for slide in normalized[2:]]


@pytest.mark.parametrize(
    "title",
    [
        "Discussion Findings",
        "Roadmap Execution Risks",
        "Overview of Customer Results",
    ],
)
def test_normalize_deck_preserves_nonstructural_keyword_titles(title: str):
    slides = [
        _slide(1, "Cover", variant="cover"),
        _slide(2, title),
        _slide(3, "Tail Analysis"),
    ]

    normalized = normalize_deck(slides, max_count=6)

    assert normalized[1].title == "Presentation Agenda"
    assert title in [slide.title for slide in normalized[2:-1]]


def test_normalize_deck_rejects_sparse_generated_chapter_numbers():
    slides = [
        _slide(1, "Cover", variant="cover"),
        _slide(2, "Market Size"),
        _slide(3, "Platform"),
        _slide(4, "Funding"),
    ]
    for slide, chapter_number in zip(slides[1:], [2, 2, 4], strict=True):
        slide.chapter_number = chapter_number
        slide.chapter_title = f"Generated Chapter {chapter_number}"

    normalized = normalize_deck(slides, max_count=7)

    assert [slide.chapter_number for slide in normalized[2:-1]] == [1, 2, 3]
    assert [slide.chapter_title for slide in normalized[2:-1]] == [
        "Market Size",
        "Platform",
        "Funding",
    ]


def test_normalize_deck_skips_agenda_when_max_count_cannot_fit_full_structure():
    normalized = normalize_deck(
        [_slide(1, "Cover", variant="cover"), _slide(2, "Plan")],
        max_count=2,
    )

    assert [slide.title for slide in normalized] == ["Cover", "Thank You"]
    assert normalized[-1].notes == ""
    assert normalized[-1].visual_direction is None

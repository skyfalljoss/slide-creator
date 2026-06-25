from app.models.schemas import SlideData
from app.services.media.image_prompts import (
    PROMPT_SUFFIX,
    build_image_prompt,
    sanitize_prompt,
)

BANNED_WORDS = ["infographic", "chart", "diagram", "comparison", "bullet", "slide", "table"]


def _slide(title, bullets=None, layout="content"):
    return SlideData(index=2, title=title, bullets=bullets or [], notes="", layout=layout)


def test_customer_experience_maps_to_contact_center_prompt():
    prompt = build_image_prompt(_slide("Improving Customer Experience with Chatbots"))
    assert "contact center" in prompt
    assert prompt.endswith(PROMPT_SUFFIX)


def test_supply_chain_maps_to_warehouse_prompt():
    prompt = build_image_prompt(_slide("Supply Chain Optimization", ["Reduce warehouse costs"]))
    assert "automated warehouse" in prompt


def test_roadmap_maps_to_timeline_prompt():
    prompt = build_image_prompt(_slide("Phased Implementation Roadmap"))
    assert "timeline path" in prompt


def test_benefits_maps_to_office_tower_prompt():
    prompt = build_image_prompt(_slide("Key Benefits and Value"))
    assert "glass office tower" in prompt


def test_section_divider_maps_to_neural_network_prompt():
    prompt = build_image_prompt(_slide("The Opportunity", layout="section_divider"))
    assert "neural network" in prompt


def test_closing_maps_to_skyline_prompt():
    prompt = build_image_prompt(_slide("Closing and Call to Action"))
    assert "city skyline" in prompt


def test_unmatched_slide_uses_generic_fallback():
    prompt = build_image_prompt(_slide("Quarterly Governance Notes"))
    assert "Professional photograph representing" in prompt
    assert "Quarterly Governance Notes" in prompt


def test_all_prompts_end_with_suffix_and_have_no_banned_words():
    titles = [
        "Customer Experience",
        "Supply Chain",
        "Roadmap",
        "Benefits",
        "Closing",
        "Some Random Topic",
    ]
    for title in titles:
        prompt = build_image_prompt(_slide(title))
        assert prompt.endswith(PROMPT_SUFFIX)
        body = prompt[: -len(PROMPT_SUFFIX)].lower()
        for word in BANNED_WORDS:
            assert word not in body


def test_prompts_stay_under_60_words():
    titles = [
        "Customer Experience Strategy",
        "Supply Chain",
        "Roadmap",
        "Benefits",
        "Closing",
        "Random Topic With A Very Long And Exhaustively Descriptive Title Indeed Here",
    ]
    for title in titles:
        prompt = build_image_prompt(_slide(title))
        assert len(prompt.split()) < 60


def test_sanitizer_strips_banned_words():
    prompt = sanitize_prompt(
        "A comparison chart and infographic diagram with a data table and bullet slide"
    )
    body = prompt[: -len(PROMPT_SUFFIX)].lower()
    for word in BANNED_WORDS:
        assert word not in body
    assert prompt.endswith(PROMPT_SUFFIX)


def test_visual_direction_is_never_used():
    slide = _slide("Random Topic")
    slide.visual_direction = "comparison chart diagram infographic UNIQUETOKEN12345"
    prompt = build_image_prompt(slide)
    assert "UNIQUETOKEN12345" not in prompt


def test_authored_image_prompt_is_preferred_and_sanitized():
    slide = _slide("Anything")
    slide.image_prompt = "A photo of a bank lobby with a comparison chart and a diagram on the wall"
    prompt = build_image_prompt(slide)
    body = prompt[: -len(PROMPT_SUFFIX)].lower()
    for word in BANNED_WORDS:
        assert word not in body
    assert "bank lobby" in prompt
    assert prompt.endswith(PROMPT_SUFFIX)


def test_blank_authored_image_prompt_falls_back_to_theme_map():
    slide = _slide("Supply Chain Optimization")
    slide.image_prompt = "   "
    prompt = build_image_prompt(slide)
    assert "automated warehouse" in prompt


def test_build_stock_query_strips_banned_and_stopwords():
    from app.services.media.image_prompts import build_stock_query

    slide = _slide("Why Citi Chart of the Market")
    query = build_stock_query(slide)
    assert "chart" not in query.lower()
    assert "why" not in query.lower().split()
    assert query.strip()


def test_build_stock_query_defaults_when_empty():
    from app.services.media.image_prompts import build_stock_query

    slide = _slide("the of and")
    assert build_stock_query(slide) == "corporate business abstract"


def test_build_stock_query_prefers_authored_image_query():
    from app.services.media.image_prompts import build_stock_query

    slide = _slide("Why Solar Is Winning")
    slide.image_query = "solar panels rooftop sunset"
    assert build_stock_query(slide) == "solar panels rooftop sunset"


def test_build_stock_query_sanitizes_authored_image_query():
    from app.services.media.image_prompts import build_stock_query

    slide = _slide("Anything")
    slide.image_query = "the bar chart of solar panels"
    query = build_stock_query(slide)
    assert "chart" not in query.lower()
    assert "the" not in query.lower().split()
    assert "solar panels" in query

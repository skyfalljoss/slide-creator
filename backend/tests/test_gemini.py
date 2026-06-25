import pytest
from app.services.generation.gemini import GeminiService
from app.models.schemas import GenerateRequest, SlideData


@pytest.mark.asyncio
async def test_generate_sales_returns_9_slides():
    gemini = GeminiService()
    req = GenerateRequest(prompt="Pitch deck", deck_type="sales_9")
    slides = await gemini.generate(req)
    assert len(slides) == 9
    assert slides[0].index == 1
    assert slides[0].layout == "title"
    assert slides[0].variant == "cover"
    assert slides[-1].title == "Thank You"
    assert slides[-1].variant == "closing"
    assert slides[0].visual_direction
    variants = {slide.variant for slide in slides}
    assert {"big_statement", "split_image", "big_stat", "comparison_table", "process", "closing"} <= variants
    assert any(slide.blocks for slide in slides)


@pytest.mark.asyncio
async def test_generate_internal_returns_6_slides():
    gemini = GeminiService()
    req = GenerateRequest(prompt="Internal review", deck_type="internal_6")
    slides = await gemini.generate(req)
    assert len(slides) == 6
    assert len({slide.variant for slide in slides if slide.variant}) >= 4
    assert slides[-1].title == "Thank You"


@pytest.mark.asyncio
async def test_refine_updates_title():
    gemini = GeminiService()
    current = SlideData(index=3, title="Situation", bullets=["Bullet 1"], notes="", layout="content")
    refine_req = type("RefineReq", (), {"session_id": "", "slide_index": 3, "instruction": "shorter"})()
    result = await gemini.refine(refine_req, current)
    assert "Refined" in result.title
    assert "refined" in result.bullets[0]
    assert result.visual_direction


@pytest.mark.asyncio
async def test_script_mode_generates_slides_from_source():
    gemini = GeminiService()
    script = (
        "Market Overview\nThe regional market is growing. Demand is strong.\n\n"
        "Our Solution\nWe offer a phased rollout. It reduces risk. Costs stay low.\n\n"
        "Next Steps\nReview the proposal. Approve the budget."
    )
    req = GenerateRequest(prompt=script, deck_type="sales_9", source_type="script")
    slides = await gemini.generate(req)

    assert len(slides) == 3
    assert slides[0].layout == "title"
    assert [s.index for s in slides] == [1, 2, 3]
    # Original chunk text is preserved in speaker notes.
    assert "regional market is growing" in slides[0].notes
    # Bullets are capped.
    assert all(len(s.bullets) <= 5 for s in slides)

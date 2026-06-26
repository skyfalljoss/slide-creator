import pytest

from app.config import settings
from app.models.schemas import GenerateRequest, RefineRequest, SlideData
from app.services.generation.gemini_api import GeminiApiService, GeminiConfigurationError, GeminiResponseError


def test_gemini_api_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")

    with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY"):
        GeminiApiService()


def test_gemini_prompt_forbids_invented_chart_data(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()

    prompt = service.build_generation_prompt(
        GenerateRequest(prompt="Create a revenue deck", deck_type="sales_9"),
        upload_summary={"filename": "metrics.csv", "columns": ["Quarter", "Revenue"], "row_count": 2},
    )

    assert "Do not invent chart values" in prompt
    assert "Uploaded CSV/XLSX is the only allowed chart data source" in prompt
    assert "Return JSON only" in prompt


def test_gemini_parser_validates_slide_count(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()

    with pytest.raises(GeminiResponseError, match="Expected 3-20 slides"):
        service.parse_slides_response(
            '{"slides":[{"index":1,"title":"Only one","bullets":[],"notes":"","layout":"title"}]}',
            deck_type="sales_9",
        )


def test_gemini_parser_accepts_structured_slide_json(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    slides_json = {
        "slides": [
            {
                "index": i,
                "title": f"Slide {i}",
                "bullets": ["Insight-driven bullet"],
                "notes": "Speaker note.",
                "layout": "content" if i > 1 else "title",
                "visual_direction": "Use Citi-style hierarchy and clean whitespace.",
            }
            for i in range(1, 10)
        ]
    }

    slides = service.parse_slides_response(service.to_json(slides_json), deck_type="sales_9")

    assert len(slides) == 9
    assert slides[0].visual_direction == "Use Citi-style hierarchy and clean whitespace."


@pytest.mark.asyncio
async def test_generate_retries_when_gemini_returns_invalid_json(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    valid_response = service.to_json(
        {
            "slides": [
                {
                    "index": i,
                    "title": f"Slide {i}",
                    "bullets": ["Insight-driven bullet"],
                    "notes": "Speaker note.",
                    "layout": "content" if i > 1 else "title",
                }
                for i in range(1, 10)
            ]
        }
    )
    responses = iter(['{"slides": [{bad: true}]}', valid_response])
    prompts: list[str] = []

    async def fake_generate_json(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    monkeypatch.setattr(service, "_generate_json", fake_generate_json)

    slides = await service.generate(GenerateRequest(prompt="Create a deck", deck_type="sales_9"))

    assert len(slides) == 9
    assert len(prompts) == 2
    assert "previous response could not be parsed" in prompts[1]


@pytest.mark.asyncio
async def test_generate_falls_back_to_local_generator_after_retry_failures(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()

    async def fake_generate_json(prompt: str) -> str:
        del prompt
        return '{"slides": [{bad: true}]}'

    monkeypatch.setattr(service, "_generate_json", fake_generate_json)

    slides = await service.generate(GenerateRequest(prompt="Create a deck", deck_type="sales_9"))

    assert len(slides) == 9
    assert slides[0].title == "Client Name Proposal"


def test_bullets_not_truncated(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    slides_json = {
        "slides": [
            {
                "index": i,
                "title": f"Slide {i}",
                "bullets": [f"Bullet {n}" for n in range(8)] if i == 2 else ["One"],
                "notes": "",
                "layout": "content" if i > 1 else "title",
            }
            for i in range(1, 10)
        ]
    }
    slides = service.parse_slides_response(service.to_json(slides_json), deck_type="sales_9")
    assert len(slides[1].bullets) == 8


def test_script_prompt_contains_processing_rules(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    prompt = service.build_script_prompt(
        GenerateRequest(prompt="Paragraph one.\n\nParagraph two.", deck_type="sales_9", source_type="script")
    )
    assert "Chunking" in prompt
    assert "original, detailed source text" in prompt
    assert "CALLOUT" in prompt
    assert "NARRATIVE_CONTEXT" in prompt
    assert "Return JSON only" in prompt
    assert "Paragraph one." in prompt


def test_script_parse_allows_variable_count_and_reindexes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    slides_json = {
        "slides": [
            {"index": 9, "title": "A", "bullets": ["x"], "notes": "n", "layout": "title"},
            {"index": 3, "title": "B", "bullets": ["y"], "notes": "n", "layout": "content"},
            {"index": 7, "title": "C", "bullets": ["z"], "notes": "n", "layout": "content"},
        ]
    }
    slides = service.parse_slides_response(service.to_json(slides_json), deck_type="sales_9", enforce_count=False)
    assert [s.index for s in slides] == [1, 2, 3]


def test_script_parse_rejects_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    with pytest.raises(GeminiResponseError, match="no slides"):
        service.parse_slides_response('{"slides":[]}', deck_type="sales_9", enforce_count=False)


def test_audience_tone_injected_into_prompts(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()

    academic = service.build_generation_prompt(
        GenerateRequest(prompt="X", deck_type="sales_9", target_audience="academic")
    )
    assert "academic audience" in academic

    casual_script = service.build_script_prompt(
        GenerateRequest(prompt="Para one.", deck_type="sales_9", source_type="script", target_audience="casual")
    )
    assert "general audience" in casual_script

    # Default is corporate.
    default = service.build_generation_prompt(GenerateRequest(prompt="X", deck_type="sales_9"))
    assert "corporate executives" in default


def test_generation_prompt_includes_subtitle_field(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    prompt = service.build_generation_prompt(GenerateRequest(prompt="X", deck_type="sales_9"))
    assert '"subtitle"' in prompt
    assert "title and section_divider slides" in prompt
    assert '"image_query"' in prompt
    assert "stock-photo search" in prompt
    assert '"kicker"' in prompt
    assert "eyebrow label" in prompt
    assert '"blocks"' in prompt
    assert "Component blocks" in prompt


def test_generation_prompt_includes_framework_variant_rules(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()

    prompt = service.build_generation_prompt(GenerateRequest(prompt="X", deck_type="sales_9"))

    assert '"variant"' in prompt
    assert "presentation-framework.html" in prompt
    assert "split_image" in prompt
    assert "big_stat" in prompt
    assert "comparison_table" in prompt
    assert "alternating light slides with darker emphasis slides" in prompt
    assert 'final slide titled "Thank You"' in prompt
    assert "Do not overuse cards" in prompt


def test_refine_prompt_uses_full_framework_schema(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    current = SlideData(
        index=2,
        title="Current state",
        kicker="CONTEXT",
        subtitle="Supporting line",
        bullets=["Point"],
        notes="Speaker notes",
        layout="content",
        variant="split_image",
        blocks=[{"type": "cards", "items": [{"title": "A", "body": "B"}]}],
        image_prompt="Concrete photo prompt",
        image_query="office workflow automation",
    )

    prompt = service.build_refine_prompt(
        RefineRequest(session_id="s1", slide_index=2, instruction="make stronger"),
        current,
    )

    assert '"variant"' in prompt
    assert '"blocks"' in prompt
    assert '"kicker"' in prompt
    assert '"subtitle"' in prompt
    assert '"image_prompt"' in prompt
    assert '"image_query"' in prompt
    assert "Framework variant rules" in prompt
    assert "Component blocks" in prompt
    assert "Preserve the slide index" in prompt


def test_gemini_parser_preserves_variant_and_blocks(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    slides_json = {
        "slides": [
            {
                "index": i,
                "title": f"Slide {i}",
                "bullets": ["Insight-driven bullet"],
                "notes": "Speaker note.",
                "layout": "content" if i > 1 else "title",
                "variant": "big_stat" if i == 2 else None,
                "blocks": [{"type": "stat", "value": "48%", "label": "Cost reduction"}] if i == 2 else None,
            }
            for i in range(1, 10)
        ]
    }

    slides = service.parse_slides_response(service.to_json(slides_json), deck_type="sales_9")

    assert slides[1].variant == "big_stat"
    assert slides[1].blocks == [{"type": "stat", "value": "48%", "label": "Cost reduction"}]


def test_gemini_parser_accepts_deck_count_within_three_slide_window(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    slides_json = {
        "slides": [
            {
                "index": i + 10,
                "title": f"Slide {i}",
                "bullets": ["Insight-driven bullet"],
                "notes": "Speaker note.",
                "layout": "content" if i > 1 else "title",
            }
            for i in range(1, 7)
        ]
    }

    slides = service.parse_slides_response(service.to_json(slides_json), deck_type="sales_9")

    assert len(slides) == 6
    assert [slide.index for slide in slides] == [1, 2, 3, 4, 5, 6]


def test_gemini_parser_rejects_deck_count_outside_three_slide_window(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    slides_json = {
        "slides": [
            {
                "index": i,
                "title": f"Slide {i}",
                "bullets": ["Insight-driven bullet"],
                "notes": "Speaker note.",
                "layout": "content" if i > 1 else "title",
            }
            for i in range(1, 3)
        ]
    }

    with pytest.raises(GeminiResponseError, match="Expected 3-20 slides"):
        service.parse_slides_response(service.to_json(slides_json), deck_type="sales_9")


def test_gemini_parser_accepts_single_block_object(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    slides_json = {
        "slides": [
            {
                "index": i,
                "title": f"Slide {i}",
                "bullets": ["Insight-driven bullet"],
                "notes": "Speaker note.",
                "layout": "content" if i > 1 else "title",
                "blocks": {
                    "type": "bullets",
                    "items": ["Reduce manual work.", "Lower operational overhead."],
                } if i == 2 else None,
            }
            for i in range(1, 10)
        ]
    }

    slides = service.parse_slides_response(service.to_json(slides_json), deck_type="sales_9")

    assert slides[1].blocks == [
        {
            "type": "bullets",
            "items": ["Reduce manual work.", "Lower operational overhead."],
        }
    ]

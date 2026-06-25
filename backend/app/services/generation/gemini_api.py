import asyncio
import json
import re
from typing import Any
from urllib import error, parse, request

from pydantic import ValidationError

from app.config import settings
from app.models.schemas import GenerateRequest, RefineRequest, SlideData

SLIDE_COUNTS = {"sales_9": 9, "internal_6": 6}
SLIDE_COUNT_TOLERANCE = 3
MAX_BULLETS = 5
MAX_SCRIPT_SLIDES = 20

_CHART_RULES = """Critical chart rules:
- Uploaded CSV/XLSX is the only allowed chart data source.
- Do not invent chart values, categories, labels, totals, or series.
- If recommending a chart, only reference columns present in the uploaded data summary.
- If no uploaded data exists, set chart_recommendation to null."""

_IMAGE_RULES = """Image prompt rules (image_prompt field):
- Write a short prompt for an AI image generator that illustrates the slide's theme.
- Describe ONLY a photorealistic photograph or an abstract artwork scene.
- NEVER request text, labels, words, charts, diagrams, infographics, tables, or bullet points (AI image models render these as garbled text).
- Describe a concrete scene, lighting, color palette, and mood. Keep it under 30 words.
- Prefer corporate/abstract imagery in blue and navy tones.
- Also provide image_query: 3-6 plain keywords describing a concrete, photographable subject for stock-photo search (e.g. "solar panels rooftop sunset"). No text, charts, or abstract concepts."""

_LAYOUTS_LINE = "Allowed layouts: title, executive_summary, content, chart, section_divider, next_steps."

_VARIANT_RULES = """Framework variant rules:
- Use presentation-framework.html as the visual reference for native editable PPTX structure.
- Set variant to one of: cover, big_statement, three_points, split_image, big_stat, before_after, comparison_table, process, quote, closing.
- Use cover for the first title slide.
- Use closing for a separate final slide titled "Thank You"; put concrete next steps on the preceding process/next_steps slide when the deck length allows.
- Create visual rhythm by alternating light slides with darker emphasis slides; big_statement, big_stat, quote, and closing are best for dark-background treatment.
- Use split_image when a narrative slide benefits from a strong right-side visual.
- Use big_stat for one dominant metric; use comparison_table for capability/vendor comparisons; use process for timelines; use quote for a vision/client quote.
- Do not overuse cards. Use three_points/cards only for true pillars, differentiators, or parallel points.
- Always provide bullets as fallback content even when blocks is present."""

_COMPONENT_RULES = """Component blocks (blocks field) — think like a UI designer choosing a React component:
For each CONTENT slide, choose the ONE component that best presents the material and return it as a single-item list. Available components:
- {"type":"cards","columns":3,"items":[{"title":"Velocity","body":"One concise sentence.","icon":"speed"}]} — 2-4 feature/pillar/point cards. Each item may set an icon keyword (speed, security, growth, global, process, quality, innovation, client, data).
- {"type":"stat","value":"48%","label":"Reduction in infrastructure costs"} — a single headline metric.
- {"type":"quote","text":"...","author":"Name - Title"} — a pull quote.
- {"type":"table","headers":["Feature","Legacy","New"],"rows":[["Compliance","Manual","Native"]]} — a comparison table.
- {"type":"process","steps":[{"title":"Audit","body":"..."}]} — 2-4 sequential steps.
- {"type":"bullets","items":["..."]} — plain bullet fallback.
Pick the component that matches the content's shape (metrics -> stat, comparisons -> table, sequence -> process, parallel points -> cards).
Set blocks to null for title, executive_summary, section_divider, and chart slides. Always also fill bullets as a fallback."""

_AUDIENCE_TONES = {
    "corporate": "Audience: corporate executives. Use a polished, board-ready, professional tone.",
    "casual": "Audience: a general audience. Use a clear, friendly, plain-language tone.",
    "academic": "Audience: an academic audience. Use a precise, formal, evidence-based tone.",
}


def _audience_tone(audience: str) -> str:
    return _AUDIENCE_TONES.get(audience, _AUDIENCE_TONES["corporate"])

_SCHEMA_BLOCK = """JSON schema:
{
  "slides": [
    {
      "index": 1,
      "title": "Slide title",
      "kicker": "Short uppercase eyebrow label (2-4 words)",
      "subtitle": "Short supporting line for title and section_divider slides",
      "bullets": ["Bullet"],
      "notes": "Speaker notes",
      "layout": "title",
      "variant": "cover",
      "visual_direction": "Specific layout guidance",
      "image_prompt": "Photorealistic or abstract scene description, no text or diagrams",
      "image_query": "3-6 keyword phrase for stock photo search",
      "blocks": [{"type": "cards", "columns": 3, "items": [{"title": "Point", "body": "Detail"}]}],
      "chart_recommendation": null
    }
  ]
}"""


class GeminiConfigurationError(RuntimeError):
    pass


class GeminiResponseError(RuntimeError):
    pass


class GeminiApiService:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = settings.gemini_api_key if api_key is None else api_key
        if not self.api_key:
            raise GeminiConfigurationError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
        self.model = model or settings.gemini_model

    async def generate(self, req: GenerateRequest, chart_data: dict | None = None, upload_summary: dict | None = None) -> list[SlideData]:
        del chart_data
        if req.source_type == "script":
            prompt = self.build_script_prompt(req, upload_summary=upload_summary)
            raw_text = await self._generate_json(prompt)
            return self.parse_slides_response(raw_text, deck_type=req.deck_type, enforce_count=False)
        prompt = self.build_generation_prompt(req, upload_summary=upload_summary)
        raw_text = await self._generate_json(prompt)
        return self.parse_slides_response(raw_text, deck_type=req.deck_type)

    async def refine(self, req: RefineRequest, current_slide: SlideData) -> SlideData:
        prompt = self.build_refine_prompt(req, current_slide)
        raw_text = await self._generate_json(prompt)
        slides = self.parse_slides_response(raw_text, deck_type="single")
        if len(slides) != 1:
            raise GeminiResponseError("Expected exactly one refined slide")
        refined = slides[0]
        refined.index = current_slide.index
        refined.chart_data = current_slide.chart_data
        refined.chart_audit = current_slide.chart_audit
        return refined

    def build_generation_prompt(self, req: GenerateRequest, upload_summary: dict | None = None) -> str:
        slide_count = SLIDE_COUNTS[req.deck_type]
        min_count = max(1, slide_count - SLIDE_COUNT_TOLERANCE)
        max_count = slide_count + SLIDE_COUNT_TOLERANCE
        upload_text = self.to_json(upload_summary or {"filename": None, "columns": [], "row_count": 0, "preview": ""})
        return f"""
You are creating a Citi-style investment banking presentation.

Return JSON only. Do not include markdown fences, commentary, or prose outside JSON.
Deck type: {req.deck_type}
Target slide count: {slide_count}
Acceptable slide count range: {min_count}-{max_count}
{_audience_tone(req.target_audience)}
User prompt: {req.prompt}
Uploaded data summary: {upload_text}

{_CHART_RULES}

Style rules:
- Write concise investment-banking slide titles with a clear takeaway.
- Provide a short kicker for every slide: a 2-4 word uppercase eyebrow label that categorizes the slide (e.g. "MARKET CONTEXT", "OUR SOLUTION").
- Provide a short subtitle for the title slide and section dividers (leave it null elsewhere).
- Use professional, client-ready language.
- Bullets must be concise and implication-led.
- Use at most {MAX_BULLETS} bullets per slide to avoid death by PowerPoint.
- Include speaker notes for each slide.
- Include visual_direction for each slide describing deterministic layout/visual treatment.

{_IMAGE_RULES}

{_VARIANT_RULES}

{_COMPONENT_RULES}

{_LAYOUTS_LINE}

{_SCHEMA_BLOCK}
""".strip()

    def build_script_prompt(self, req: GenerateRequest, upload_summary: dict | None = None) -> str:
        target = SLIDE_COUNTS[req.deck_type]
        upload_text = self.to_json(upload_summary or {"filename": None, "columns": [], "row_count": 0, "preview": ""})
        return f"""
You are converting a source document into a Citi-style presentation.
The source may be a blog post, speech, transcript, or meeting notes.

Return JSON only. Do not include markdown fences, commentary, or prose outside JSON.
Deck type: {req.deck_type}
Target slide count: aim for about {target} slides, but use between 3 and {MAX_SCRIPT_SLIDES} based on the document's natural structure.
{_audience_tone(req.target_audience)}

Source document:
\"\"\"
{req.prompt}
\"\"\"

Uploaded data summary: {upload_text}

Processing rules:
- Chunking: Divide the source into logical slides based on headings, paragraph groups, and narrative shifts. Each slide must cover one coherent idea.
- Summarization: Convert each chunk into at most {MAX_BULLETS} concise, implication-led bullet points. Never exceed {MAX_BULLETS} bullets. Keep bullets short to avoid death by PowerPoint.
- Title: Write a clear, punchy title for each slide that captures its key takeaway.
- Kicker: Provide a 2-4 word uppercase eyebrow label for every slide that categorizes its theme.
- Subtitle: Provide a short supporting subtitle for the title slide and any section dividers (leave it null on other slides).
- Speaker notes: Put the original, detailed source text for that chunk into the "notes" field verbatim, so the presenter keeps full context. Do not shorten or summarize the notes.
- Use a title layout for the first slide; use a next_steps layout for any closing actions.

{_CHART_RULES}

{_IMAGE_RULES}

{_VARIANT_RULES}

{_COMPONENT_RULES}

{_LAYOUTS_LINE}

{_SCHEMA_BLOCK}
""".strip()

    def build_refine_prompt(self, req: RefineRequest, current_slide: SlideData) -> str:
        return f"""
You are refining one slide in a Citi-style investment banking presentation.

Return JSON only. Do not include markdown fences, commentary, or prose outside JSON.
Refine exactly one slide using the instruction.
Instruction: {req.instruction}
Current slide JSON: {current_slide.model_dump_json()}

Do not invent chart values. Preserve the slide index.
Preserve or intentionally update framework fields so the slide remains renderable:
- kicker, subtitle, variant, blocks, visual_direction, image_prompt, and image_query.
- Keep layout within the allowed list unless the instruction explicitly changes the slide purpose.

{_IMAGE_RULES}

{_VARIANT_RULES}

{_COMPONENT_RULES}

{_LAYOUTS_LINE}

{_SCHEMA_BLOCK}
""".strip()

    def parse_slides_response(self, text: str, *, deck_type: str, enforce_count: bool = True) -> list[SlideData]:
        try:
            payload = self._loads_lenient(text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise GeminiResponseError("Gemini returned invalid JSON") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("slides"), list):
            raise GeminiResponseError("Gemini response must contain a slides array")

        try:
            slides = [SlideData.model_validate(item) for item in payload["slides"]]
        except ValidationError as exc:
            raise GeminiResponseError("Gemini slide JSON did not match the schema") from exc

        # Cap bullets on every slide to prevent "death by PowerPoint".
        for slide in slides:
            if len(slide.bullets) > MAX_BULLETS:
                slide.bullets = slide.bullets[:MAX_BULLETS]

        if not enforce_count:
            # Script mode: the content decides how many slides; just bound and reindex.
            if not slides:
                raise GeminiResponseError("Script produced no slides")
            slides = slides[:MAX_SCRIPT_SLIDES]
            for i, slide in enumerate(slides, 1):
                slide.index = i
            return slides

        if deck_type == "single":
            if len(slides) != 1:
                raise GeminiResponseError(f"Expected 1 slide, received {len(slides)}")
            slides[0].index = 1
            return slides

        expected = SLIDE_COUNTS[deck_type]
        min_count = max(1, expected - SLIDE_COUNT_TOLERANCE)
        max_count = expected + SLIDE_COUNT_TOLERANCE
        if not min_count <= len(slides) <= max_count:
            raise GeminiResponseError(f"Expected {min_count}-{max_count} slides, received {len(slides)}")
        for i, slide in enumerate(slides, 1):
            slide.index = i
        return slides

    def to_json(self, data: Any) -> str:
        return json.dumps(data, ensure_ascii=True)

    async def _generate_json(self, prompt: str) -> str:
        return await asyncio.to_thread(self._post_generate_content, prompt)

    def _post_generate_content(self, prompt: str) -> str:
        encoded_model = parse.quote(self.model, safe="")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{encoded_model}:generateContent?key={parse.quote(self.api_key)}"
        body = self.to_json(
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.35,
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 16384,
                },
            }
        ).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GeminiResponseError("Gemini API request failed") from exc

        try:
            return payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GeminiResponseError("Gemini API response did not include JSON text") from exc

    def _strip_json_fence(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.removeprefix("```json").removeprefix("```")
            stripped = stripped.removesuffix("```")
        return stripped.strip()

    def _loads_lenient(self, text: str) -> Any:
        """Parse JSON tolerantly: strip fences/prose, slice the outermost object,
        and repair trailing commas before falling back to a hard error."""
        candidate = self._strip_json_fence(text)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("no JSON object found in model output")
        sliced = candidate[start : end + 1]
        try:
            return json.loads(sliced)
        except json.JSONDecodeError:
            # Remove trailing commas (",}" / ",]") that some models emit.
            repaired = re.sub(r",(\s*[}\]])", r"\1", sliced)
            return json.loads(repaired)

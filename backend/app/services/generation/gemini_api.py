import json
import logging
import re
from typing import Any
from urllib.parse import quote

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from pydantic import ValidationError

from app.config import settings
from app.models.schemas import GenerateRequest, RefineRequest, SlideData
from app.prompts import rules as _rules
from app.prompts.generation import GENERATION_PROMPT_TEMPLATE
from app.prompts.refine import REFINE_PROMPT_TEMPLATE
from app.prompts.retry import RETRY_PROMPT_TEMPLATE
from app.prompts.script import SCRIPT_PROMPT_TEMPLATE

SLIDE_COUNTS = {"sales_9": 9, "internal_6": 6}
SLIDE_COUNT_TOLERANCE = 3
MAX_SCRIPT_SLIDES = 20
GENERATION_PARSE_ATTEMPTS = 2

logger = logging.getLogger(__name__)


class GeminiConfigurationError(RuntimeError):
    pass


class GeminiResponseError(RuntimeError):
    pass


class GeminiApiService:
    def __init__(self, api_key: str | None = None, model: str | None = None, http_client: httpx.AsyncClient | None = None):
        self.api_key = settings.gemini_api_key if api_key is None else api_key
        if not self.api_key:
            raise GeminiConfigurationError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
        self.model = model or settings.gemini_model
        self._client = http_client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            from app.dependencies import get_http_client
            self._client = get_http_client()
        return self._client

    async def generate(self, req: GenerateRequest, chart_data: dict | None = None, upload_summary: dict | None = None) -> list[SlideData]:
        del chart_data
        if req.source_type == "script":
            prompt = self.build_script_prompt(req, upload_summary=upload_summary)
            return await self._generate_with_retries(req, prompt, upload_summary=upload_summary, enforce_count=False)
        prompt = self.build_generation_prompt(req, upload_summary=upload_summary)
        return await self._generate_with_retries(req, prompt, upload_summary=upload_summary, enforce_count=True)

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
        upload_text = self.to_json(upload_summary or {"filename": None, "columns": [], "row_count": 0, "preview": ""})
        return GENERATION_PROMPT_TEMPLATE.format(
            deck_type_hint=req.deck_type or "Not specified — let the content decide",
            audience_tone=_rules.audience_tone(req.target_audience),
            prompt=req.prompt,
            upload_text=upload_text,
            chart_rules=_rules.CHART_RULES,
            title_quality_rules=_rules.TITLE_QUALITY_RULES,
            kicker_quality_rules=_rules.KICKER_QUALITY_RULES,
            bullet_quality_rules=_rules.BULLET_QUALITY_RULES,
            notes_quality_rules=_rules.NOTES_QUALITY_RULES,
            image_rules=_rules.IMAGE_RULES,
            variant_rules=_rules.VARIANT_RULES,
            component_rules=_rules.COMPONENT_RULES,
            callout_quality_rules=_rules.CALLOUT_QUALITY_RULES,
            narrative_context_rules=_rules.NARRATIVE_CONTEXT_RULES,
            layouts_line=_rules.LAYOUTS_LINE,
            schema_block=_rules.SCHEMA_BLOCK,
        )

    def build_script_prompt(self, req: GenerateRequest, upload_summary: dict | None = None) -> str:
        upload_text = self.to_json(upload_summary or {"filename": None, "columns": [], "row_count": 0, "preview": ""})
        return SCRIPT_PROMPT_TEMPLATE.format(
            deck_type_hint=req.deck_type or "Not specified — let the content decide",
            max_script_slides=MAX_SCRIPT_SLIDES,
            audience_tone=_rules.audience_tone(req.target_audience),
            prompt_quoted=f'"""\n{req.prompt}\n"""',
            upload_text=upload_text,
            title_quality_rules=_rules.TITLE_QUALITY_RULES,
            kicker_quality_rules=_rules.KICKER_QUALITY_RULES,
            bullet_quality_rules=_rules.BULLET_QUALITY_RULES,
            notes_quality_rules=_rules.NOTES_QUALITY_RULES,
            chart_rules=_rules.CHART_RULES,
            image_rules=_rules.IMAGE_RULES,
            variant_rules=_rules.VARIANT_RULES,
            component_rules=_rules.COMPONENT_RULES,
            callout_quality_rules=_rules.CALLOUT_QUALITY_RULES,
            narrative_context_rules=_rules.NARRATIVE_CONTEXT_RULES,
            layouts_line=_rules.LAYOUTS_LINE,
            schema_block=_rules.SCHEMA_BLOCK,
        )

    def build_refine_prompt(self, req: RefineRequest, current_slide: SlideData) -> str:
        return REFINE_PROMPT_TEMPLATE.format(
            instruction=req.instruction,
            current_slide_json=current_slide.model_dump_json(),
            title_quality_rules=_rules.TITLE_QUALITY_RULES,
            kicker_quality_rules=_rules.KICKER_QUALITY_RULES,
            bullet_quality_rules=_rules.BULLET_QUALITY_RULES,
            notes_quality_rules=_rules.NOTES_QUALITY_RULES,
            image_rules=_rules.IMAGE_RULES,
            variant_rules=_rules.VARIANT_RULES,
            component_rules=_rules.COMPONENT_RULES,
            callout_quality_rules=_rules.CALLOUT_QUALITY_RULES,
            narrative_context_rules=_rules.NARRATIVE_CONTEXT_RULES,
            layouts_line=_rules.LAYOUTS_LINE,
            schema_block=_rules.SCHEMA_BLOCK,
        )

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

        if not 3 <= len(slides) <= 20:
            raise GeminiResponseError(f"Expected 3-20 slides, received {len(slides)}")
        for i, slide in enumerate(slides, 1):
            slide.index = i
        return slides

    def to_json(self, data: Any) -> str:
        return json.dumps(data, ensure_ascii=True)

    async def _generate_json(self, prompt: str) -> str:
        return await self._post_generate_content(prompt)

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    )
    async def _post_generate_content(self, prompt: str) -> str:
        encoded_model = quote(self.model, safe="")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{encoded_model}:generateContent?key={quote(self.api_key)}"
        body = self.to_json(
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.35,
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 16384,
                },
            }
        )
        try:
            resp = await self._get_client().post(
                url,
                content=body,
                headers={"Content-Type": "application/json"},
                timeout=60.0,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException, ValueError) as exc:
            raise GeminiResponseError("Gemini API request failed") from exc

        try:
            return payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GeminiResponseError("Gemini API response did not include JSON text") from exc

    async def _generate_with_retries(
        self,
        req: GenerateRequest,
        prompt: str,
        *,
        upload_summary: dict | None,
        enforce_count: bool,
    ) -> list[SlideData]:
        raw_text = ""
        last_error: GeminiResponseError | None = None
        current_prompt = prompt
        for attempt in range(1, GENERATION_PARSE_ATTEMPTS + 1):
            try:
                raw_text = await self._generate_json(current_prompt)
                return self.parse_slides_response(raw_text, deck_type=req.deck_type, enforce_count=enforce_count)
            except GeminiResponseError as exc:
                last_error = exc
                logger.warning("Gemini generation attempt %s failed: %s", attempt, exc)
                current_prompt = self.build_json_retry_prompt(prompt, raw_text, str(exc))

        logger.exception("Gemini generation failed after retries; falling back to local generator", exc_info=last_error)
        return await self._fallback_generate(req, upload_summary=upload_summary)

    async def _fallback_generate(self, req: GenerateRequest, upload_summary: dict | None = None) -> list[SlideData]:
        from app.services.generation.gemini import GeminiService

        return await GeminiService().generate(req, upload_summary=upload_summary)

    def build_json_retry_prompt(self, original_prompt: str, bad_response: str, error: str) -> str:
        excerpt = bad_response[:4000] if bad_response else "<empty response>"
        return RETRY_PROMPT_TEMPLATE.format(
            error=error,
            bad_response_excerpt=excerpt,
            original_prompt=original_prompt,
        )

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

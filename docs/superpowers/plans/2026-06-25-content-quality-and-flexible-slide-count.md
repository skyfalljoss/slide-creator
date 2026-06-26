# Content Quality & Flexible Slide Count Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve slide content quality (titles, bullets, notes, images) and make slide count content-driven instead of hardcoded.

**Architecture:** Keep the existing pipeline structure. All quality changes live in `app/prompts/` — the prompt templates get stronger style rules that push the AI toward specific, data-driven content. The `deck_type` field becomes optional, and server-side count enforcement is replaced with a wide validation range (3-20 slides).

**Tech Stack:** Python 3.11, FastAPI, Pydantic, Gemini API

---

### Task 1: Update prompt rules with quality guidance constants

**Files:**
- Modify: `app/prompts/rules.py`
- Test: (verified by prompt content tests)

- [ ] **Step 1: Add quality guidance constants to rules.py**

Add new constants for title, bullet, notes, and kicker quality. Tighten existing `IMAGE_RULES`.

```python
# app/prompts/rules.py  (add after SCHEMA_BLOCK)

TITLE_QUALITY_RULES = """TITLES: Each title must state a specific, concrete takeaway — not a generic section label.
  ❌ "Process Improvement"
  ✓ "Automation unlocks faster reporting with stronger controls" """

BULLET_QUALITY_RULES = """BULLETS: Each bullet 1-2 sentences — specific enough to stand alone as a meaningful insight, short enough to scan in seconds. Ban generic phrases like "improve efficiency", "enhance performance". Each bullet must include a concrete number, percentage, dollar figure, or timeframe.
  ❌ "Improve efficiency"
  ✓ "Reduce report generation time by 60% through automated compliance checks" """

NOTES_QUALITY_RULES = """NOTES: 2-4 sentences per slide explaining the context, data sources, and the key message the presenter should convey. Don't just rephrase the bullets."""

KICKER_QUALITY_RULES = """KICKERS: Vary the kicker across slides. Each slide gets a distinct 2-4 word angle. Don't repeat the same labels."""
```

- [ ] **Step 2: Tighten IMAGE_RULES in rules.py**

Replace the existing `IMAGE_RULES` with a version that emphasizes topic-specific imagery:

```python
IMAGE_RULES = """Image prompt rules (image_prompt field):
- Write a short prompt for an AI image generator that illustrates the slide's theme.
- The image MUST be directly related to this specific slide's topic. For a slide about "Solar farm financing", use "solar panels acreage sunset clean energy installation", not a generic "corporate business meeting".
- Describe ONLY a photorealistic photograph or an abstract artwork scene.
- NEVER request text, labels, words, charts, diagrams, infographics, tables, or bullet points (AI image models render these as garbled text).
- Describe a concrete scene, lighting, color palette, and mood. Keep it under 30 words.
- Also provide image_query: 3-6 plain keywords describing a concrete, photographable subject for stock-photo search (e.g. "solar panels rooftop sunset"). No text, charts, or abstract concepts."""
```

- [ ] **Step 3: Remove subtitle rule from VARIANT_RULES (it's now in the templates)**

No change needed — the existing variant rules are fine as-is.

- [ ] **Step 4: Run lint**

```bash
cd backend && uv run ruff check app/prompts/
```

---

### Task 2: Update generation prompt template with quality guidance + flexible count

**Files:**
- Modify: `app/prompts/generation.py`
- Modify: `app/services/generation/gemini_api.py` (builder method — add new format args)

- [ ] **Step 1: Rewrite generation.py template**

Replace the current style rules and slide count wording with the quality-focused version:

```python
GENERATION_PROMPT_TEMPLATE = """You are creating a Citi-style investment banking presentation.

Return JSON only. Do not include markdown fences, commentary, or prose outside JSON.
Deck type hint: {deck_type_hint}

Slide count: Create between 4 and 15 slides depending on the depth and breadth of the user's prompt. A brief prompt may yield 4-6 slides; a detailed prompt with multiple topics may yield 10-15. Let the content's natural structure drive the count — don't force an arbitrary target.

{audience_tone}
User prompt: {prompt}
Uploaded data summary: {upload_text}

{chart_rules}

Content quality rules:
{title_quality_rules}
{kicker_quality_rules}
{bullet_quality_rules}
Use at most {max_bullets} bullets per slide.
{notes_quality_rules}
Include visual_direction for each slide describing deterministic layout/visual treatment.

{image_rules}

{variant_rules}

{component_rules}

{layouts_line}

{schema_block}"""
```

- [ ] **Step 2: Verify the template compiles**

```bash
cd backend && uv run python -c "from app.prompts.generation import GENERATION_PROMPT_TEMPLATE; print('OK')"
```

---

### Task 3: Update script prompt template with quality guidance

**Files:**
- Modify: `app/prompts/script.py`
- Modify: `app/services/generation/gemini_api.py` (builder method)

- [ ] **Step 1: Rewrite script.py template**

Replace style rules and slide count wording:

```python
SCRIPT_PROMPT_TEMPLATE = """You are converting a source document into a Citi-style presentation.
The source may be a blog post, speech, transcript, or meeting notes.

Return JSON only. Do not include markdown fences, commentary, or prose outside JSON.
Deck type hint: {deck_type_hint}

Slide count: Create between 3 and {max_script_slides} slides based on the document's natural structure — each major section or narrative shift gets its own slide. Don't force the document into an arbitrary number.

{audience_tone}

Source document:
{prompt_quoted}

Uploaded data summary: {upload_text}

Processing rules:
- Chunking: Divide the source into logical slides based on headings, paragraph groups, and narrative shifts.
- Summarization: Convert each chunk into concise, insight-driven content following the Content quality rules below.
- Speaker notes: Put the original, detailed source text for that chunk into the "notes" field verbatim, so the presenter keeps full context. Do not shorten or summarize the notes.
- Use a title layout for the first slide; use a next_steps layout for any closing actions.

Content quality rules:
{title_quality_rules}
{kicker_quality_rules}
{bullet_quality_rules}
Use at most {max_bullets} bullets per slide.
{notes_quality_rules}

{chart_rules}

{image_rules}

{variant_rules}

{component_rules}

{layouts_line}

{schema_block}"""
```

- [ ] **Step 2: Verify the template compiles**

```bash
cd backend && uv run python -c "from app.prompts.script import SCRIPT_PROMPT_TEMPLATE; print('OK')"
```

---

### Task 4: Update refine prompt template with quality guidance

**Files:**
- Modify: `app/prompts/refine.py`
- Modify: `app/services/generation/gemini_api.py` (builder method)

- [ ] **Step 1: Rewrite refine.py template**

Add content quality rules section:

```python
REFINE_PROMPT_TEMPLATE = """You are refining one slide in a Citi-style investment banking presentation.

Return JSON only. Do not include markdown fences, commentary, or prose outside JSON.
Refine exactly one slide using the instruction.
Instruction: {instruction}
Current slide JSON: {current_slide_json}

Do not invent chart values. Preserve the slide index.
Preserve or intentionally update framework fields so the slide remains renderable:
- kicker, subtitle, variant, blocks, visual_direction, image_prompt, and image_query.
- Keep layout within the allowed list unless the instruction explicitly changes the slide purpose.

Content quality rules:
{title_quality_rules}
{kicker_quality_rules}
{bullet_quality_rules}
{notes_quality_rules}

{image_rules}

{variant_rules}

{component_rules}

{layouts_line}

{schema_block}"""
```

- [ ] **Step 2: Verify the template compiles**

```bash
cd backend && uv run python -c "from app.prompts.refine import REFINE_PROMPT_TEMPLATE; print('OK')"
```

---

### Task 5: Update gemini_api.py — flexible count + quality format args

**Files:**
- Modify: `app/services/generation/gemini_api.py`
- Test: `tests/test_gemini_api.py`

- [ ] **Step 1: Update `build_generation_prompt()` to pass quality rules and flexible count**

```python
def build_generation_prompt(self, req: GenerateRequest, upload_summary: dict | None = None) -> str:
    upload_text = self.to_json(upload_summary or {"filename": None, "columns": [], "row_count": 0, "preview": ""})
    deck_hint = req.deck_type or "Not specified — let the content decide"
    return GENERATION_PROMPT_TEMPLATE.format(
        deck_type_hint=deck_hint,
        audience_tone=_rules.audience_tone(req.target_audience),
        prompt=req.prompt,
        upload_text=upload_text,
        max_bullets=MAX_BULLETS,
        chart_rules=_rules.CHART_RULES,
        image_rules=_rules.IMAGE_RULES,
        variant_rules=_rules.VARIANT_RULES,
        component_rules=_rules.COMPONENT_RULES,
        layouts_line=_rules.LAYOUTS_LINE,
        schema_block=_rules.SCHEMA_BLOCK,
        title_quality_rules=_rules.TITLE_QUALITY_RULES,
        bullet_quality_rules=_rules.BULLET_QUALITY_RULES,
        notes_quality_rules=_rules.NOTES_QUALITY_RULES,
        kicker_quality_rules=_rules.KICKER_QUALITY_RULES,
    )
```

- [ ] **Step 2: Update `build_script_prompt()` similarly**

```python
def build_script_prompt(self, req: GenerateRequest, upload_summary: dict | None = None) -> str:
    upload_text = self.to_json(upload_summary or {"filename": None, "columns": [], "row_count": 0, "preview": ""})
    deck_hint = req.deck_type or "Not specified — let the content decide"
    return SCRIPT_PROMPT_TEMPLATE.format(
        deck_type_hint=deck_hint,
        max_script_slides=MAX_SCRIPT_SLIDES,
        audience_tone=_rules.audience_tone(req.target_audience),
        prompt_quoted=f'"""\n{req.prompt}\n"""',
        upload_text=upload_text,
        max_bullets=MAX_BULLETS,
        chart_rules=_rules.CHART_RULES,
        image_rules=_rules.IMAGE_RULES,
        variant_rules=_rules.VARIANT_RULES,
        component_rules=_rules.COMPONENT_RULES,
        layouts_line=_rules.LAYOUTS_LINE,
        schema_block=_rules.SCHEMA_BLOCK,
        title_quality_rules=_rules.TITLE_QUALITY_RULES,
        bullet_quality_rules=_rules.BULLET_QUALITY_RULES,
        notes_quality_rules=_rules.NOTES_QUALITY_RULES,
        kicker_quality_rules=_rules.KICKER_QUALITY_RULES,
    )
```

- [ ] **Step 3: Update `build_refine_prompt()` to pass quality rules**

```python
def build_refine_prompt(self, req: RefineRequest, current_slide: SlideData) -> str:
    return REFINE_PROMPT_TEMPLATE.format(
        instruction=req.instruction,
        current_slide_json=current_slide.model_dump_json(),
        image_rules=_rules.IMAGE_RULES,
        variant_rules=_rules.VARIANT_RULES,
        component_rules=_rules.COMPONENT_RULES,
        layouts_line=_rules.LAYOUTS_LINE,
        schema_block=_rules.SCHEMA_BLOCK,
        title_quality_rules=_rules.TITLE_QUALITY_RULES,
        bullet_quality_rules=_rules.BULLET_QUALITY_RULES,
        notes_quality_rules=_rules.NOTES_QUALITY_RULES,
        kicker_quality_rules=_rules.KICKER_QUALITY_RULES,
    )
```

- [ ] **Step 4: Remove strict count enforcement in `parse_slides_response()`**

Remove the SLIDE_COUNTS-based validation for non-script, non-single modes. Use a wide range instead:

```python
# In parse_slides_response, replace the strict count block at lines 157-161:
if deck_type != "single":
    if not 3 <= len(slides) <= 20:
        raise GeminiResponseError(f"Expected 3-20 slides, received {len(slides)}")
```

- [ ] **Step 5: Remove unused SLIDE_COUNTS references in the method**

The `build_generation_prompt()` no longer uses `SLIDE_COUNTS`, `SLIDE_COUNT_TOLERANCE`, `slide_count`, `min_count`, or `max_count`. Remove those local variables. Leave the module-level constants (`SLIDE_COUNTS`, `SLIDE_COUNT_TOLERANCE`, `MAX_BULLETS`, `MAX_SCRIPT_SLIDES`, `GENERATION_PARSE_ATTEMPTS`) in place — they're imported by routers.

- [ ] **Step 6: Run lint**

```bash
cd backend && uv run ruff check app/services/generation/gemini_api.py
```

---

### Task 6: Update gemini.py local fallback — handle optional deck_type

**Files:**
- Modify: `app/services/generation/gemini.py`

- [ ] **Step 1: Update `_mock_slides()` to handle `None` or unknown deck_type**

```python
def _mock_slides(deck_type: str | None) -> list[SlideData]:
    if deck_type == "internal_6":
        return [...]  # existing internal_6 mock
    # Default mock (used for sales_9, None, or any other value)
    return [...]  # existing sales_9 mock
```

The mock data quality itself isn't critical here — it's the fallback when Gemini is unavailable. The actual improvement comes from the Gemini prompt.

- [ ] **Step 2: Run tests**

```bash
cd backend && uv run pytest tests/test_gemini_api.py -v --tb=short
```

---

### Task 7: Schema — make deck_type optional in GenerateRequest

**Files:**
- Modify: `app/models/schemas.py`
- Test: `tests/test_api.py` (update test data)

- [ ] **Step 1: Change `deck_type` field from Literal to optional str**

```python
class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=50000)
    deck_type: str | None = None
    source_type: Literal["brief", "script"] = "brief"
    target_audience: Literal["corporate", "casual", "academic"] = "corporate"
    theme: Literal["minimalist", "bold", "dark"] = "minimalist"
    aspect_ratio: Literal["16:9", "4:3"] = "16:9"
    file_id: str | None = None
```

- [ ] **Step 2: Run lint**

```bash
cd backend && uv run ruff check app/models/schemas.py
```

---

### Task 8: Update routers to handle optional deck_type

**Files:**
- Modify: `app/routers/generate.py`
- Modify: `app/routers/export.py`

- [ ] **Step 1: Update `_max_slide_count()` in `generate.py`**

```python
def _max_slide_count(req: GenerateRequest) -> int:
    if req.source_type == "script":
        return MAX_SCRIPT_SLIDES
    if req.deck_type and req.deck_type in SLIDE_COUNTS:
        return SLIDE_COUNTS[req.deck_type] + SLIDE_COUNT_TOLERANCE
    return MAX_SCRIPT_SLIDES  # 20 — flexible cap
```

- [ ] **Step 2: Update `export.py` to handle missing deck_type in session**

In `export.py`, find the line that reads `session["deck_type"]` and handle it gracefully:

```python
# Find the line similar to:
max_count = SLIDE_COUNTS.get(session.get("deck_type"), len(session["slides"]) + 1) + SLIDE_COUNT_TOLERANCE
```

Use `.get()` with a sensible default instead of `session["deck_type"]`.

- [ ] **Step 3: Run lint**

```bash
cd backend && uv run ruff check app/routers/
```

---

### Task 9: Update tests

**Files:**
- Modify: `tests/test_gemini_api.py`
- Modify: `tests/test_api.py`
- (if needed) `tests/test_providers.py`

- [ ] **Step 1: Update `test_gemini_api.py` for new parse_slides_response range**

Update tests that expect the old strict count enforcement. The test `test_gemini_parser_validates_slide_count` should expect 3-20 range instead of 6-12:

```python
def test_gemini_parser_validates_slide_count(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()

    # 1 slide is still invalid (below 3 minimum)
    with pytest.raises(GeminiResponseError, match="Expected 3-20 slides"):
        service.parse_slides_response(
            '{"slides":[{"index":1,"title":"Only one","bullets":[],"notes":"","layout":"title"}]}',
            deck_type="sales_9",
        )
```

And `test_gemini_parser_accepts_deck_count_within_three_slide_window` — 6 slides should still pass (it's within 3-20). `test_gemini_parser_rejects_deck_count_outside_three_slide_window` — 4 slides is now valid (within 3-20). Update the assertion or remove the test:

```python
def test_gemini_parser_rejects_deck_count_outside_three_slide_window(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    slides_json = {"slides": [...]}  # 4 slides

    # 4 slides is now within the 3-20 range — this should pass
    slides = service.parse_slides_response(service.to_json(slides_json), deck_type="sales_9")
    assert len(slides) == 4
```

Or update the test to use 2 slides (below minimum).

- [ ] **Step 2: Update `test_api.py` — update GenerateRequest usage with deck_type**

Find all `GenerateRequest(prompt=..., deck_type="sales_9")` calls in tests. Since `deck_type` is now optional with a default of `None`, the existing calls still compile. But update any tests that depend on the strict count behavior.

Also update the `test_generate_resolves_images_for_framework_visual_variants` test if it uses deck_type for count logic.

- [ ] **Step 3: Run all tests**

```bash
cd backend && uv run pytest tests/ -v --tb=short
```

Expected: 261 passed.

---

### Task 10: Final verification

**Files:** (all modified files)

- [ ] **Step 1: Run lint on all changed files**

```bash
cd backend && uv run ruff check app/ tests/
```

- [ ] **Step 2: Run full test suite**

```bash
cd backend && uv run pytest tests/ -v --tb=short
```

- [ ] **Step 3: Verify app starts and generates**

```bash
cd backend && uv run python -c "
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
# Test generate without deck_type
r = client.post('/api/v1/generate', json={'prompt': 'Create a deck about solar energy'})
print(r.status_code, r.json().get('session_id', ''), 'slides:', len(r.json().get('slides', [])))
"
```


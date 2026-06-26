# Content-Flexible Slides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich slide content with deeper bullets, expanded speaker notes, a highlighted callout field, and presenter context — removing all hard truncation limits.

**Architecture:** Schema adds two optional fields (`callout`, `narrative_context`). Prompt quality rules expand to allow 2-4 sentence bullets and 5-10 sentence notes. PPTX rendering removes all `bullets[:N]` slicing and renders callout as an accent box. Model-side `MAX_BULLETS=5` truncation is removed.

**Tech Stack:** Python 3.11, Pydantic, python-pptx, FastAPI

---

### Task 1: Schema — Add callout + narrative_context to SlideData

**Files:**
- Modify: `app/models/schemas.py:107-128`

- [ ] **Step 1: Read the file**

Run: `cat app/models/schemas.py`

- [ ] **Step 2: Add two optional fields to SlideData**

Add after `narrative_context` field:

```python
    callout: str | None = None
    narrative_context: str | None = None
```

Insert right after `image_query` (line 125) and before `content` (line 126).

Target edit location:
```python
    image_query: str | None = None
    callout: str | None = None
    narrative_context: str | None = None
    content: SlideContent | None = None
```

- [ ] **Step 3: Verify the file parses**

Run: `uv run python -c "from app.models.schemas import SlideData; s = SlideData(index=1, title='Test', bullets=[], notes='', layout='content'); print('ok:', s.callout, s.narrative_context)"`
Expected: `ok: None None`

- [ ] **Step 4: Commit**

Run: `git add -A && git commit -m "feat: add callout and narrative_context fields to SlideData"`

---

### Task 2: Quality Rules — Expand BULLET/NOTES, add CALLOUT/NARRATIVE_CONTEXT

**Files:**
- Modify: `app/prompts/rules.py`

- [ ] **Step 1: Replace BULLET_QUALITY_RULES**

Old:
```python
BULLET_QUALITY_RULES = """BULLETS: Each bullet 1-2 sentences — specific enough to stand alone as a meaningful insight, short enough to scan in seconds. Ban generic phrases like "improve efficiency", "enhance performance". Each bullet must include a concrete number, percentage, dollar figure, or timeframe.
  ❌ "Improve efficiency"
  ✓ "Reduce report generation time by 60% through automated compliance checks" """
```

New:
```python
BULLET_QUALITY_RULES = """BULLETS: Each bullet 2-4 sentences with supporting evidence, concrete examples, and data points. Each bullet must be a complete, self-contained insight the presenter could read aloud. Ban generic filler like "improve efficiency" without quantification.
  ❌ "Improve efficiency"
  ✓ "Reduce report generation time by 60% through automated compliance checks, saving 120 hours per quarter across the compliance team — equivalent to $48,000 in annual cost avoidance at blended fully-loaded rates."
  A bullet about a market trend should cite timeframe, magnitude, and a concrete example. A bullet about a recommendation should state expected impact and reference supporting evidence. Use sub-bullet structure within a single bullet when appropriate (list examples, comparisons, or data points inline)."""

```

- [ ] **Step 2: Replace NOTES_QUALITY_RULES**

Old:
```python
NOTES_QUALITY_RULES = """NOTES: 2-4 sentences per slide explaining the context, data sources, and the key message the presenter should convey. Don't just rephrase the bullets."""
```

New:
```python
NOTES_QUALITY_RULES = """NOTES: 5-10 sentences per slide. Structure your notes as:
1. Context sentence — what led to this slide and how it fits in the overall narrative
2. Key message — the single most important thing the audience should take away
3. Data sources and methodology — 2-3 sentences explaining where the numbers come from, timeframes, methodology notes
4. Anticipated audience questions — 1-2 likely questions with suggested responses
5. Delivery guidance — pace, emphasis, tone cues for the presenter
Do not just rephrase the bullets. The notes should prepare the presenter for the full discussion."""

```

- [ ] **Step 3: Add CALLOUT_QUALITY_RULES**

Add after KICKER_QUALITY_RULES:
```python
CALLOUT_QUALITY_RULES = """CALLOUT: For every content slide (layout: content), provide a `callout` field with one sentence that captures the single most important takeaway. This should work as a headline or pull-quote — the one thing the audience must remember. Set callout to null for title, section_divider, and thank-you slides."""
```

- [ ] **Step 4: Add NARRATIVE_CONTEXT_RULES**

Add after CALLOUT_QUALITY_RULES:
```python
NARRATIVE_CONTEXT_RULES = """NARRATIVE_CONTEXT (optional): For complex slides, provide a `narrative_context` field with 2-4 sentences of background context — market conditions, methodology notes, data provenance, strategic rationale. This is stored for presenter reference and does NOT appear on the slide. Set to null for simple slides where bullets and notes already convey full context."""
```

- [ ] **Step 5: Update SCHEMA_BLOCK**

Add callout and narrative_context to the JSON schema example:
```python
SCHEMA_BLOCK = """JSON schema:
{
  "slides": [
    {
      "index": 1,
      "title": "Slide title",
      "kicker": "Short uppercase eyebrow label (2-4 words)",
      "subtitle": "Short supporting line for title and section_divider slides",
      "bullets": ["Bullet with evidence and data"],
      "notes": "Speaker notes",
      "layout": "title",
      "variant": "cover",
      "visual_direction": "Specific layout guidance",
      "image_prompt": "Photorealistic or abstract scene description, no text or diagrams",
      "image_query": "3-6 keyword phrase for stock photo search",
      "blocks": [{"type": "cards", "columns": 3, "items": [{"title": "Point", "body": "Detail"}]}],
      "chart_recommendation": null,
      "callout": "Key takeaway sentence for content slides, null otherwise",
      "narrative_context": "Optional 2-4 sentence background for presenter (null for simple slides)"
    }
  ]
}"""
```

- [ ] **Step 6: Verify file parses**

Run: `uv run python -c "exec(open('app/prompts/rules.py').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit**

Run: `git add -A && git commit -m "feat: expand quality rules for richer bullets, notes, callout, narrative context"`

---

### Task 3: Generation Template — Remove max_bullets, add callout/context rules

**Files:**
- Modify: `app/prompts/generation.py`

- [ ] **Step 1: Rewrite generation.py**

Replace entire file content:

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
Use 3-12 bullets per slide — let the topic's depth determine the count. A simple point may need 3; a complex argument may need 10-12.
{notes_quality_rules}
{callout_quality_rules}
{narrative_context_rules}
Include visual_direction for each slide describing deterministic layout/visual treatment.

{image_rules}

{variant_rules}

{component_rules}

{layouts_line}

{schema_block}"""
```

- [ ] **Step 2: Commit**

Run: `git add -A && git commit -m "feat: update generation template with callout/context rules and flexible bullets"`

---

### Task 4: Script Template — Same updates

**Files:**
- Modify: `app/prompts/script.py`

- [ ] **Step 1: Rewrite script.py**

Replace `max_bullets` reference in content quality section. The current template has:
```
Content quality rules:
{title_quality_rules}
{kicker_quality_rules}
{bullet_quality_rules}
Use at most {max_bullets} bullets per slide.
{notes_quality_rules}
```

Replace with:
```
Content quality rules:
{title_quality_rules}
{kicker_quality_rules}
{bullet_quality_rules}
Use 3-12 bullets per slide — let the topic's depth determine the count.
{notes_quality_rules}
{callout_quality_rules}
{narrative_context_rules}
```

Also add `{callout_quality_rules}` and `{narrative_context_rules}` to the template format string.

The template should now have these format placeholders:
```python
SCRIPT_PROMPT_TEMPLATE = """...
{chart_rules}

Content quality rules:
{title_quality_rules}
{kicker_quality_rules}
{bullet_quality_rules}
Use 3-12 bullets per slide — let the topic's depth determine the count.
{notes_quality_rules}
{callout_quality_rules}
{narrative_context_rules}

{chart_rules}

{image_rules}

{variant_rules}

{component_rules}

{layouts_line}

{schema_block}"""
```

- [ ] **Step 2: Commit**

Run: `git add -A && git commit -m "feat: update script template with callout/context rules and flexible bullets"`

---

### Task 5: Refine Template — Same updates + preservation logic

**Files:**
- Modify: `app/prompts/refine.py`

- [ ] **Step 1: Rewrite refine.py**

Replace `max_bullets` with flexible count:
```python
REFINE_PROMPT_TEMPLATE = """You are refining one slide in a Citi-style investment banking presentation.

Return JSON only. Do not include markdown fences, commentary, or prose outside JSON.
Refine exactly one slide using the instruction.
Instruction: {instruction}
Current slide JSON: {current_slide_json}

Do not invent chart values. Preserve the slide index.
Preserve or intentionally update framework fields so the slide remains renderable:
- kicker, subtitle, variant, blocks, visual_direction, image_prompt, image_query, callout, and narrative_context.
- Keep layout within the allowed list unless the instruction explicitly changes the slide purpose.

Content quality rules:
{title_quality_rules}
{kicker_quality_rules}
{bullet_quality_rules}
{notes_quality_rules}
{callout_quality_rules}
{narrative_context_rules}

{image_rules}

{variant_rules}

{component_rules}

{layouts_line}

{schema_block}"""
```

- [ ] **Step 2: Commit**

Run: `git add -A && git commit -m "feat: update refine template with callout/context rules"`

---

### Task 6: gemini_api.py — Remove MAX_BULLETS, remove truncation, pass new rules

**Files:**
- Modify: `app/services/generation/gemini_api.py`

- [ ] **Step 1: Remove MAX_BULLETS and bullet truncation**

Remove line: `MAX_BULLETS = 5` (line 22)

Remove the truncation block (lines 141-144):
```python
        # Cap bullets on every slide to prevent "death by PowerPoint".
        for slide in slides:
            if len(slide.bullets) > MAX_BULLETS:
                slide.bullets = slide.bullets[:MAX_BULLETS]
```

- [ ] **Step 2: Add new prompt variables to build_generation_prompt**

In `build_generation_prompt`, add these format kwargs:
```python
import app.prompts.rules as _rules
...
    def build_generation_prompt(
        self, req: GenerateRequest, upload_summary: dict | None = None
    ) -> str:
        ...
        return GENERATION_PROMPT_TEMPLATE.format(
            deck_type_hint=deck_type_hint,
            audience_tone=_rules.audience_tone(req.target_audience),
            prompt=req.prompt,
            upload_text=upload_text,
            chart_rules=_rules.CHART_RULES,
            title_quality_rules=_rules.TITLE_QUALITY_RULES,
            kicker_quality_rules=_rules.KICKER_QUALITY_RULES,
            bullet_quality_rules=_rules.BULLET_QUALITY_RULES,
            notes_quality_rules=_rules.NOTES_QUALITY_RULES,
            callout_quality_rules=_rules.CALLOUT_QUALITY_RULES,
            narrative_context_rules=_rules.NARRATIVE_CONTEXT_RULES,
            max_bullets=MAX_BULLETS,  # REMOVE THIS LINE
            image_rules=_rules.IMAGE_RULES,
            ...
        )
```

Replace `max_bullets=MAX_BULLETS,` with the two new rules and remove the `max_bullets` variable.

- [ ] **Step 3: Also update build_script_prompt**

Same change — remove `max_bullets=MAX_BULLETS,` and add:
```python
            callout_quality_rules=_rules.CALLOUT_QUALITY_RULES,
            narrative_context_rules=_rules.NARRATIVE_CONTEXT_RULES,
```

- [ ] **Step 4: Update build_refine_prompt**

Same change — add the two new rules.

- [ ] **Step 5: Commit**

Run: `git add -A && git commit -m "feat: remove MAX_BULLETS, remove truncation, add callout/context rules to prompts"`

---

### Task 7: gemini.py mock — Update for richer content + new fields

**Files:**
- Modify: `app/services/generation/gemini.py`

- [ ] **Step 1: Remove MAX_BULLETS from mock**

Remove line: `MAX_BULLETS = 5` (line 5)

- [ ] **Step 2: Update _mock_slides to include callout + narrative_context**

In the mock slide creation, change the bullet generation to produce richer bullets and add callout/narrative_context.

Find the existing bullet generation (around lines 60-90) and update to produce 4-6 bullets with richer content and add callout/narrative_context to each slide.

Example updated mock data (add these fields to every generated slide):
```python
    slides = [
        SlideData(
            index=1,
            title="Strategic Growth Through Digital Transformation",
            kicker="EXECUTIVE OVERVIEW",
            subtitle="",
            bullets=[
                "Digital transformation initiatives across Southeast Asia are projected to unlock $1.2 trillion in enterprise value by 2028, driven by cloud migration, AI adoption, and regulatory modernization across the region's six largest economies.",
                "Our client's current digital maturity index of 3.2/5.0 lags behind the regional average of 4.1/5.0, representing a measurable gap of $180M in potential annual revenue capture from underutilized digital channels.",
                "The three-year roadmap targets a 2.1x return on digital investment through phased automation of core banking processes, customer experience upgrades, and data infrastructure modernization across 12 operational markets.",
            ],
            notes="Context: This is the opening strategic slide that sets the tone for the entire presentation. Key message: Digital transformation is not optional — the gap is quantified and the opportunity is material. Data sources: BCG Digital Maturity Index 2025, client internal IT audit Q1 2026. Anticipated question: 'How was the $1.2T figure derived?' — This comes from BCG's Southeast Asia Digital Economy Report, which aggregates World Bank, McKinsey, and national ICT ministry data. Delivery: Lead with the $1.2T figure, pause, then contrast with the 3.2 vs 4.1 gap. Emphasize 'not optional'.",
            layout="content",
            variant="cover",
            visual_direction="Dark background with a large stat callout showing 2.1x ROI",
            image_prompt="Aerial view of Singapore financial district at golden hour with digital network overlay connecting skyscrapers",
            image_query="Singapore skyline digital overlay finance",
            callout="$1.2 trillion in enterprise value at stake — and our client is currently below regional maturity baseline.",
            narrative_context="This deck was prepared for the Q2 2026 board review. The digital maturity index comparison uses the BCG DMI v4 framework, last updated January 2026. All revenue projections are in constant 2025 USD and assume no major regulatory changes in the 2026-2028 window.",
        ),
    ]
```

Every slide in _mock_slides should get:
- `callout` — a meaningful takeaway sentence
- `narrative_context` — 2-4 sentences of context (or null for simpler slides)

And `_script_mock_slides` should get the same treatment.

- [ ] **Step 3: Commit**

Run: `git add -A && git commit -m "feat: update mock slides with callout, narrative_context, and richer bullets"`

---

### Task 8: PPTX Canvas — Add add_callout_box()

**Files:**
- Modify: `app/services/presentation/pptx_canvas.py`

- [ ] **Step 1: Add the callout rendering method**

Add this method to `PptxCanvas` class, after `add_bullets_box` (after line 101):

```python
    def add_callout_box(
        self,
        slide,
        text: str,
        left: float,
        top: float,
        width: float,
        height: float,
    ) -> None:
        """Rendered as an accent-bordered highlight box — the single key takeaway."""
        box = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            self.ix(left),
            self.iy(top),
            self.ix(width),
            self.iy(height),
        )
        box.fill.solid()
        box.fill.fore_color.rgb = self._active_theme().accent_soft
        box.line.color.rgb = self._active_theme().accent
        box.line.width = Pt(1.5)
        box.shadow.inherit = False
        try:
            box.adjustments[0] = 0.08
        except (IndexError, TypeError, ValueError):
            logger.debug("Failed to adjust callout corner radius", exc_info=True)

        tf = box.text_frame
        self.clear_text_frame(tf)
        p = tf.paragraphs[0]
        p.text = text
        p.font.name = BODY_FONT
        p.font.size = Pt(14)
        p.font.italic = True
        p.font.color.rgb = self._active_theme().text
        p.font.bold = False
        p.alignment = PP_ALIGN.LEFT
```

- [ ] **Step 2: Verify the file parses**

Run: `uv run python -c "from app.services.presentation.pptx_canvas import PptxCanvas; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

Run: `git add -A && git commit -m "feat: add callout box rendering to PPTX canvas"`

---

### Task 9: PPTX Layouts — Remove bullet truncation, add callout rendering

**Files:**
- Modify: `app/services/presentation/pptx_layouts.py`

- [ ] **Step 1: Title slide — show ALL bullets**

Line 42-49: Change secondary truncation from `secondary[:3]` to all bullets.

Old (lines 42-49):
```python
        subtitle = data.subtitle or (data.bullets[0] if data.bullets else "")
        secondary = data.bullets if data.subtitle else data.bullets[1:]
        subtitle_top = accent_top + 0.25
        if subtitle:
            self._add_text(slide, LAYOUT.left_margin, subtitle_top, 9.0, 0.8, subtitle, 22, self.theme.muted)
        if secondary:
            secondary_top = subtitle_top + (0.92 if subtitle else 0)
            self._add_bullets_box(slide, secondary[:3], LAYOUT.left_margin, secondary_top, 9.2, 1.15)
```

New:
```python
        subtitle = data.subtitle or (data.bullets[0] if data.bullets else "")
        secondary = data.bullets if data.subtitle else data.bullets[1:]
        subtitle_top = accent_top + 0.25
        if subtitle:
            self._add_text(slide, LAYOUT.left_margin, subtitle_top, 9.0, 0.8, subtitle, 22, self.theme.muted)
        if secondary:
            secondary_top = subtitle_top + (0.92 if subtitle else 0)
            self._add_bullets_box(slide, secondary, LAYOUT.left_margin, secondary_top, 9.2, 2.5)
```

- [ ] **Step 2: big_statement variant — show ALL bullets**

Line 66: Change `data.bullets[0]` to `data.bullets`.

Old:
```python
            self._add_text(slide, LAYOUT.left_margin, 6.25, 11.5, 0.75, data.bullets[0], 22, self.theme.muted)
```

New:
```python
            bullet_text = "\n".join(data.bullets)
            self._add_card_text(slide, LAYOUT.left_margin, 6.25, 11.5, 2.5, bullet_text, 18, self.theme.muted)
```

- [ ] **Step 3: three_points variant — first 3 as cards, rest as detail**

Line 75: Change from `data.bullets[:3]` to keep first 3 as cards, add rest as detail list.

Old:
```python
        items = [{"title": item, "body": ""} for item in data.bullets[:3]]
```

New:
```python
        card_items = data.bullets[:3]
        extra_items = data.bullets[3:]
        items = [{"title": item, "body": ""} for item in card_items]
```

After the card grid (line ~90), add:
```python
        if extra_items:
            detail_top = top + 3.5  # below card grid
            self._add_bullets_box(slide, extra_items, LAYOUT.left_margin, detail_top, LAYOUT.content_width, 1.5)
```

- [ ] **Step 4: split_image variant — show ALL bullets**

Line 101: Change `data.bullets[:4]` to `data.bullets`.

Old:
```python
                self._add_bullets_box(slide, data.bullets[:4], left, text_top, 7.2, 3.0)
```

New:
```python
                self._add_bullets_box(slide, data.bullets, left, text_top, 7.2, 4.0)
```

- [ ] **Step 5: big_stat variant — show ALL bullets as supporting detail**

Line 124: Change to use all bullets as body text below the stat.

Old:
```python
            label = data.subtitle or (data.bullets[0] if data.bullets else "")
```

New:
```python
            label = data.subtitle or (data.bullets[0] if data.bullets else "")
            remaining = data.bullets[1:] if data.subtitle else data.bullets[1:]
```

After the stat value rendering (around line 130), add:
```python
            if remaining:
                self._add_bullets_box(slide, remaining, LAYOUT.left_margin, 5.5, LAYOUT.content_width, 2.5)
```

- [ ] **Step 6: before_after — already uses all bullets, no change needed**

Lines 151-152 already split all bullets with `bullets[:mid]` and `bullets[mid:]`. No change.

- [ ] **Step 7: process variant — first 4 as steps, rest as additional detail**

Line 175: Keep first 4 as steps, render remaining as bullets.

Old:
```python
            {"steps": [{"title": item, "body": ""} for item in data.bullets[:4]]},
```

New:
```python
            process_steps = [{"title": item, "body": ""} for item in data.bullets[:4]]
            extra_items = data.bullets[4:]
```

After the process block rendering (around line 180), add:
```python
            if extra_items:
                self._add_bullets_box(slide, extra_items, LAYOUT.left_margin, 5.5, LAYOUT.content_width, 1.5)
```

Use `process_steps` instead of inline list.

- [ ] **Step 8: closing variant — show ALL bullets**

Line 210: Change `data.bullets[:3]` to `data.bullets`.

Old:
```python
            self._add_bullets_box(slide, data.bullets[:3], LAYOUT.left_margin, 6.35, 9.0, 1.6)
```

New:
```python
            self._add_bullets_box(slide, data.bullets, LAYOUT.left_margin, 6.35, 9.0, 2.5)
```

- [ ] **Step 9: next_steps variant — show all bullets**

Lines 304-324: Change to use all bullets as cards (up to 5) and rest as timeline.

Old:
```python
        steps = bullets[:3]
```

New:
```python
        steps = bullets[:5]
```

(Keep remaining bullets as timeline text — line 320 `bullets[3:]` stays but change to `bullets[5:]`).

- [ ] **Step 10: standard content — show ALL bullets, remove "+N remaining"**

Line 400: Change `items[:5]` to `items`.

Old:
```python
        self._add_bullets_box(slide, items[:5], LAYOUT.left_margin + 0.55, top + 0.95, 9.4, panel_h - 1.25)
        if len(items) > 5:
            self._add_text(slide, LAYOUT.left_margin + 0.55, top + panel_h - 0.45, 8.5, 0.35, f"+ {len(items) - 5} additional points", 13, self.theme.muted)
```

New:
```python
        self._add_bullets_box(slide, items, LAYOUT.left_margin + 0.55, top + 0.95, 9.4, panel_h - 1.25)
```

- [ ] **Step 11: Add callout rendering to standard content**

In `_apply_standard_content` (around line 340), after `_add_content_header`, check for callout:

Old:
```python
    def _apply_standard_content(self, slide: Slide, data: SlideData) -> None:
        top = self._add_content_header(slide, data.title, getattr(data, "kicker", None))
        if data.bullets:
            self._add_modern_bullet_panel(slide, data.bullets, top)
        else:
            self._add_visual_panel(slide, data, LAYOUT.left_margin, top, LAYOUT.content_width, LAYOUT.content_bottom - top)
```

New:
```python
    def _apply_standard_content(self, slide: Slide, data: SlideData) -> None:
        top = self._add_content_header(slide, data.title, getattr(data, "kicker", None))
        if data.callout:
            self._add_callout_box(slide, data.callout, LAYOUT.left_margin, top, LAYOUT.content_width, 0.6)
            top += 0.85
        if data.bullets:
            self._add_modern_bullet_panel(slide, data.bullets, top)
        else:
            self._add_visual_panel(slide, data, LAYOUT.left_margin, top, LAYOUT.content_width, LAYOUT.content_bottom - top)
```

- [ ] **Step 12: Commit**

Run: `git add -A && git commit -m "feat: remove bullet truncation in PPTX layouts, add callout rendering"`

---

### Task 10: PPTX Engine — Ensure narrative_context appended to notes

**Files:**
- Modify: `app/services/presentation/pptx_engine.py`

- [ ] **Step 1: Find where notes are set**

Search for `notes_slide` or `speaker_notes` in pptx_engine.py. The engine should append `narrative_context` after the main notes, separated by a divider.

- [ ] **Step 2: Append narrative_context to notes if present**

In the slide rendering loop, after setting `notes_text_frame.text = slide.notes`, add:
```python
            if getattr(slide, "narrative_context", None):
                notes_text_frame.text += "\n\n---\n\n" + slide.narrative_context
```

- [ ] **Step 3: Commit**

Run: `git add -A && git commit -m "feat: append narrative_context to PPTX speaker notes"`

---

### Task 11: Tests — Update for richer bullets + new fields

**Files:**
- Modify: Various test files that reference SlideData, MAX_BULLETS, or bullet counts

- [ ] **Step 1: Find all test files referencing MAX_BULLETS or bullet truncation**

Run: `grep -rn "MAX_BULLETS" tests/`

- [ ] **Step 2: Find tests that hardcode bullet counts**

Run: `grep -rn "len(slides" tests/`

- [ ] **Step 3: Update tests referencing MAX_BULLETS**

Replace `from app.services.generation.gemini_api import MAX_BULLETS` or similar with the removal. If any test asserts MAX_BULLETS == 5, remove that assertion.

- [ ] **Step 4: Update gemini_api tests**

Find `tests/test_gemini_api.py` and update any test that validates bullet truncation behavior. Remove tests that check for the `+ N additional points` overflow message.

- [ ] **Step 5: Update PPTX tests that check bullet counts**

Run: `grep -rn "bullets\[:" tests/test_pptx_layouts.py tests/test_pptx_engine.py`

Update any assertion that expects truncated bullet count. Instead assert that all bullets are rendered or that callout appears.

- [ ] **Step 6: Run the full suite**

Run: `uv run ruff check app/ tests/ && uv run pytest tests/ -q --tb=short`
Expected: All checks pass, 261 tests pass (or close to it; may slightly differ from pre-existing count)

- [ ] **Step 7: Fix any failures**

Iterate on test failures until all pass.

- [ ] **Step 8: Commit**

Run: `git add -A && git commit -m "test: update tests for content-flexible slides"`

---

### Task 12: Final Verification

**No specific files — run full verification suite.**

- [ ] **Step 1: Lint check**

Run: `uv run ruff check app/ tests/`
Expected: All checks passed

- [ ] **Step 2: Full test suite**

Run: `uv run pytest tests/ -q --tb=short`
Expected: All tests pass

- [ ] **Step 3: Smoke test with local provider**

Run: `AI_PROVIDER=local STORAGE_PROVIDER=local SESSION_PROVIDER=local uv run python -c "
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
r = client.post('/api/v1/generate', json={'prompt': 'Solar energy expansion in Southeast Asia'})
data = r.json()
slides = data.get('slides', [])
print('Slides:', len(slides))
for s in slides:
    print(f'  Slide {s[\"index\"]}: {s[\"title\"]}')
    print(f'    callout: {s.get(\"callout\", \"N/A\")}')
    print(f'    bullets: {len(s.get(\"bullets\", []))}')
print('OK')
"`
Expected: Slides have callout field populated, bullets > 5 on some slides

- [ ] **Step 4: Frontend typecheck**

Run: `cd ../frontend && pnpm exec tsc -b`
Expected: No type errors (SlideData changes may not affect frontend, but verify)

- [ ] **Step 5: Commit if all pass**

Run: `git add -A && git commit -m "chore: final verification"`

---

## Self-Review Checklist

- [ ] Spec coverage: Every slide layout truncation point identified and changed
- [ ] Placeholder check: No TBD/TODO
- [ ] Type consistency: callout/narrative_context fields consistent across schema → mock → tests
- [ ] All PPTX layouts with bullet slicing are updated

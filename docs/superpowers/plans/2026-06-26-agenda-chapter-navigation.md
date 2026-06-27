# Agenda Chapter Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `Today's Discussion` with a bounded `Presentation Agenda` and show the active agenda chapter on every related content slide.

**Architecture:** Chapter metadata travels with `SlideData` from generation through persistence, preview, refinement, and PPTX export. The deck normalizer owns agenda construction and deterministic fallback chapter assignment; the PPTX engine renders chapter navigation after each layout-specific body so all variants receive it consistently.

**Tech Stack:** Python 3.11, FastAPI/Pydantic, python-pptx, pytest, React 19, TypeScript 6, Vitest.

---

## File Map

- Modify `backend/app/models/schemas.py`: add validated chapter metadata to slide schemas.
- Modify `frontend/src/types/index.ts`: preserve chapter metadata in frontend state and saved decks.
- Modify `backend/app/prompts/rules.py`: request `Presentation Agenda`, concise descriptions, and chapter assignments.
- Modify `backend/app/prompts/refine.py`: preserve chapter metadata during slide refinement.
- Modify `backend/app/services/generation/deck_normalizer.py`: create the agenda, derive concise descriptions, and normalize chapter assignments.
- Modify `backend/app/services/presentation/pptx_engine.py`: render one universal post-layout chapter marker.
- Modify `backend/app/services/presentation/pptx_layouts.py`: implement bounded agenda cards and chapter-aware header spacing.
- Modify `backend/app/templates/presentation-framework.html`: align the HTML visual reference with the agenda and chapter marker.
- Modify `backend/tests/test_schemas.py`: validate chapter fields.
- Modify `backend/tests/test_deck_normalizer.py`: test agenda copy and chapter grouping.
- Modify `backend/tests/test_pptx_engine.py`: test geometry and marker coverage across variants.

### Task 1: Add Chapter Metadata To The Shared Slide Contract

**Files:**
- Modify: `backend/app/models/schemas.py:65-135`
- Modify: `frontend/src/types/index.ts:27-49`
- Modify: `backend/app/prompts/rules.py:17-65`
- Modify: `backend/app/prompts/refine.py:1-25`
- Test: `backend/tests/test_schemas.py`

- [ ] **Step 1: Write failing schema tests**

```python
import pytest
from pydantic import ValidationError

from app.models.schemas import SlideData


def test_slide_data_accepts_agenda_chapter_metadata():
    slide = SlideData(
        index=3,
        title="Market Opportunity",
        bullets=[],
        notes="",
        layout="content",
        chapter_number=1,
        chapter_title="Market Opportunity",
    )

    assert slide.chapter_number == 1
    assert slide.chapter_title == "Market Opportunity"


def test_slide_data_rejects_chapter_number_outside_agenda_range():
    with pytest.raises(ValidationError):
        SlideData(
            index=3,
            title="Market Opportunity",
            bullets=[],
            notes="",
            layout="content",
            chapter_number=5,
        )
```

- [ ] **Step 2: Run the schema tests and verify RED**

Run: `cd backend && uv run pytest tests/test_schemas.py -k chapter -v`

Expected: FAIL because `chapter_number` and `chapter_title` are not declared fields.

- [ ] **Step 3: Add the backend and frontend fields**

Add to both `SlideContent` and `SlideData` in `backend/app/models/schemas.py`:

```python
chapter_number: int | None = Field(default=None, ge=1, le=4)
chapter_title: str | None = Field(default=None, max_length=80)
```

Add to `SlideData` in `frontend/src/types/index.ts`:

```typescript
chapter_number?: number | null
chapter_title?: string | null
```

- [ ] **Step 4: Update generation and refinement contracts**

Replace the overview rule in `VARIANT_RULES` with:

```text
- Add exactly one overview slide immediately after the cover titled "Presentation Agenda", using process variant with 3-4 chapters. Each chapter needs a 2-5 word title and an 8-14 word description. Do not create another agenda, outline, overview, roadmap, or discussion slide.
- Set chapter_number (1-4) and chapter_title on every content slide except the agenda and final closing slide. Related slides must repeat the same chapter metadata.
```

Add these fields to `SCHEMA_BLOCK`:

```json
"chapter_number": 1,
"chapter_title": "Market Opportunity"
```

Add `chapter_number` and `chapter_title` to the field-preservation list in `backend/app/prompts/refine.py`.

- [ ] **Step 5: Verify GREEN and frontend type safety**

Run: `cd backend && uv run pytest tests/test_schemas.py -k chapter -v`

Expected: 2 passed.

Run: `cd frontend && pnpm build`

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 6: Commit the contract change**

```bash
git add backend/app/models/schemas.py backend/app/prompts/rules.py backend/app/prompts/refine.py backend/tests/test_schemas.py frontend/src/types/index.ts
git commit -m "feat: add agenda chapter metadata"
```

### Task 2: Normalize One Professional Agenda And Its Chapters

**Files:**
- Modify: `backend/app/services/generation/deck_normalizer.py:1-185`
- Test: `backend/tests/test_deck_normalizer.py`

- [ ] **Step 1: Write failing normalization tests**

```python
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
    assert all(slide.chapter_title for slide in content)
    assert content[0].chapter_title == content[1].chapter_title


def test_normalize_agenda_uses_concise_source_copy_without_generic_sentence():
    slides = [_slide(1, "Cover", variant="cover"), _slide(2, "Market Opportunity")]
    slides[1].callout = "Short-video demand is expanding as creators seek faster production workflows across major platforms."

    normalized = normalize_deck(slides, max_count=5)
    steps = normalized[1].blocks[0]["steps"]

    assert steps[0]["body"] != "The context and core insight for the discussion."
    assert len(steps[0]["body"]) <= 90
```

Add a third test where generated slides already carry chapter metadata and assert normalization preserves the assignments and uses their ordered chapter titles.

- [ ] **Step 2: Run the normalization tests and verify RED**

Run: `cd backend && uv run pytest tests/test_deck_normalizer.py -k "professional_agenda or concise_source_copy or preserves_generated_chapters" -v`

Expected: FAIL because the title is still `Today's Discussion` and chapter fields are unset.

- [ ] **Step 3: Rename the agenda constants and recognition rules**

Use:

```python
AGENDA_TITLE = "Presentation Agenda"
MAX_CHAPTERS = 4
AGENDA_TITLES = ("agenda", "outline", "overview", "roadmap", "discussion")
```

Normalize any recognized overview-like slide to `AGENDA_TITLE`, clear its own chapter metadata, and continue removing duplicates.

- [ ] **Step 4: Implement deterministic chapter assignment**

Add focused helpers with these signatures:

```python
def _assign_chapters(slides: list[SlideData], agenda: SlideData) -> list[tuple[int, str, str]]: ...
def _content_for_chapters(slides: list[SlideData], agenda: SlideData) -> list[SlideData]: ...
def _fallback_chapter_number(position: int, slide_count: int, chapter_count: int) -> int: ...
def _agenda_description(slide: SlideData) -> str: ...
def _concise(text: str, *, max_words: int, max_chars: int) -> str: ...
```

Use the fallback formula:

```python
chapter_number = min((position * chapter_count) // slide_count + 1, chapter_count)
```

where `position` is zero-based and `chapter_count = min(MAX_CHAPTERS, len(content_slides))`. When valid generated chapter metadata exists, preserve its nondecreasing 1-4 assignments and fill missing slides from the preceding valid chapter. Derive each chapter title from generated `chapter_title` or the first slide assigned to that chapter.

Build agenda steps from the resulting chapter definitions:

```python
agenda.blocks = [{
    "type": "process",
    "steps": [
        {"title": title, "body": description}
        for _, title, description in chapter_definitions
    ],
}]
agenda.bullets = [title for _, title, _ in chapter_definitions]
```

Description source priority is `callout`, `subtitle`, first bullet, then `Key context, evidence, and decisions for this chapter.`. Normalize to at most 14 words and 90 characters without leaving a partial word.

- [ ] **Step 5: Run normalization tests and verify GREEN**

Run: `cd backend && uv run pytest tests/test_deck_normalizer.py -v`

Expected: all normalizer tests pass with `Presentation Agenda` assertions.

- [ ] **Step 6: Update API assertions affected by the title**

Replace `Today's Discussion` expectations with `Presentation Agenda` in `backend/tests/test_api.py`, and assert generated content slides include chapter metadata:

```python
assert data["slides"][1]["title"] == "Presentation Agenda"
assert all(slide["chapter_number"] for slide in data["slides"][2:-1])
```

Run: `cd backend && uv run pytest tests/test_api.py -k generate -v`

Expected: all selected API tests pass.

- [ ] **Step 7: Commit the normalizer change**

```bash
git add backend/app/services/generation/deck_normalizer.py backend/tests/test_deck_normalizer.py backend/tests/test_api.py
git commit -m "feat: normalize presentation agenda chapters"
```

### Task 3: Render Bounded Agenda Cards

**Files:**
- Modify: `backend/app/services/presentation/pptx_layouts.py:186-253`
- Test: `backend/tests/test_pptx_engine.py:1170-1210`

- [ ] **Step 1: Write a failing agenda geometry test**

```python
def test_presentation_agenda_keeps_long_copy_inside_cards():
    slides = [
        SlideData(index=1, title="Cover", bullets=[], notes="", layout="title"),
        SlideData(
            index=2,
            title="Presentation Agenda",
            bullets=["Market Opportunity", "Product & Technology", "Business Model", "Investment & Outlook"],
            notes="",
            layout="content",
            variant="process",
            blocks=[{
                "type": "process",
                "steps": [{"title": f"Chapter {index}", "body": "A deliberately long agenda description " * 8} for index in range(1, 5)],
            }],
        ),
    ]

    prs = Presentation(BytesIO(PptxEngine().render(slides)))
    agenda = prs.slides[1]
    card_shapes = [shape for shape in agenda.shapes if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE]
    description_boxes = [shape for shape in agenda.shapes if shape.has_text_frame and "deliberately long" in shape.text]

    assert len(description_boxes) == 4
    for box in description_boxes:
        containing_cards = [card for card in card_shapes if card.left <= box.left and card.top <= box.top and card.left + card.width >= box.left + box.width and card.top + card.height >= box.top + box.height]
        assert containing_cards
```

- [ ] **Step 2: Run the geometry test and verify RED**

Run: `cd backend && uv run pytest tests/test_pptx_engine.py::test_presentation_agenda_keeps_long_copy_inside_cards -v`

Expected: FAIL because the special renderer still keys off `Today's Discussion` or its text regions exceed the cards.

- [ ] **Step 3: Implement the selected Option A layout**

Rename `_apply_discussion_overview` and related helpers to agenda terminology. Detect `Presentation Agenda`, render a 2x2 grid, and keep all text boxes within fixed regions:

```python
number_box = (x + 0.55, y + 0.32, 1.5, 0.55)
title_box = (x + 0.55, y + 1.12, cw - 1.1, 0.62)
body_box = (x + 0.55, y + 1.82, cw - 1.1, 0.55)
body_size = 13 if len(body) > 72 else 14 if len(body) > 48 else 15
```

Use cleaned, normalized input; never recreate `The context and core insight for the discussion.` in the renderer. The renderer fallback must be `Key context, evidence, and decisions for this chapter.`.

- [ ] **Step 4: Run agenda rendering tests and verify GREEN**

Run: `cd backend && uv run pytest tests/test_pptx_engine.py -k agenda -v`

Expected: agenda title, four card numbers, and geometry tests pass.

- [ ] **Step 5: Commit bounded agenda rendering**

```bash
git add backend/app/services/presentation/pptx_layouts.py backend/tests/test_pptx_engine.py
git commit -m "fix: keep agenda content within cards"
```

### Task 4: Render The Active Chapter On Every Content Variant

**Files:**
- Modify: `backend/app/services/presentation/pptx_engine.py:165-205`
- Modify: `backend/app/services/presentation/pptx_layouts.py:456-480`
- Test: `backend/tests/test_pptx_engine.py`

- [ ] **Step 1: Write failing cross-variant marker tests**

Create one parametrized test for `big_statement`, `three_points`, `split_image`, `big_stat`, `before_after`, `comparison_table`, `process`, and `quote`. Each slide gets:

```python
chapter_number=2,
chapter_title="Product & Technology",
```

Render each slide and assert both `02` and `PRODUCT & TECHNOLOGY` exist. Add a chart-data case and a separate omission test for cover, `Presentation Agenda`, and closing slides.

- [ ] **Step 2: Run the marker tests and verify RED**

Run: `cd backend && uv run pytest tests/test_pptx_engine.py -k chapter_marker -v`

Expected: special variants and chart routes fail because only `_add_content_header` currently adds a number.

- [ ] **Step 3: Move marker rendering to the engine dispatch boundary**

Replace the index-based `_add_section_number` with:

```python
def _add_chapter_marker(self, slide: Slide, data: SlideData) -> None:
    if not data.chapter_number or not data.chapter_title:
        return
    if data.variant == "closing" or clean_inline_text(data.title).lower() == "presentation agenda":
        return
    number = f"{data.chapter_number:02d}"
    self._add_text(slide, 0.83, 0.22, 0.65, 0.42, number, 18, self._active_theme().accent, bold=True)
    self._add_text(slide, 1.55, 0.26, 5.2, 0.34, data.chapter_title.upper(), 11, self._active_theme().muted, bold=True)
```

Extract the existing dispatch branches into `_apply_content_body(slide, data)`. Keep `_apply_content_slide` as the single wrapper:

```python
def _apply_content_slide(self, slide: Slide, data: SlideData) -> None:
    self._current_slide_data = data
    self._apply_content_body(slide, data)
    self._add_chapter_marker(slide, data)
```

Remove marker calls from `_add_content_header` so standard layouts do not duplicate it.

- [ ] **Step 4: Reserve header space without breaking special layouts**

When chapter metadata exists, use these standard header positions:

```python
if kicker:
    kicker_top, title_top, rule_top = 0.78, 1.18, 1.96
else:
    title_top, rule_top = 0.86, 1.78
```

Keep special-variant title positions that already begin below `0.75`. The big-stat kicker remains at `0.82`, below the marker row ending at `0.64`.

- [ ] **Step 5: Run marker and full PPTX tests**

Run: `cd backend && uv run pytest tests/test_pptx_engine.py -k chapter_marker -v`

Expected: all marker tests pass.

Run: `cd backend && uv run pytest tests/test_pptx_engine.py -v`

Expected: all PPTX tests pass.

- [ ] **Step 6: Commit universal chapter navigation**

```bash
git add backend/app/services/presentation/pptx_engine.py backend/app/services/presentation/pptx_layouts.py backend/tests/test_pptx_engine.py
git commit -m "feat: show active agenda chapter on content slides"
```

### Task 5: Align The HTML Reference And Verify End To End

**Files:**
- Modify: `backend/app/templates/presentation-framework.html`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Update the HTML visual reference**

Add a `Presentation Agenda` example using the approved 2x2 card treatment and a reusable chapter marker at the top of subsequent content slides:

```html
<div class="chapter-marker"><strong>01</strong><span>MARKET OPPORTUNITY</span></div>
```

Use fixed card regions and text limits matching the PPTX renderer. Do not add decorative gradient orbs or duplicate overview slides.

- [ ] **Step 2: Run backend lint and tests**

Run: `cd backend && uv run ruff check app/ tests/`

Expected: `All checks passed!`

Run: `cd backend && uv run pytest`

Expected: all tests pass.

- [ ] **Step 3: Run frontend tests and production build**

Run: `cd frontend && pnpm test`

Expected: all Vitest tests pass.

Run: `cd frontend && pnpm build`

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 4: Generate and inspect a representative deck**

Use a fixture containing eight content slides across four chapters and export it through `PptxEngine`. Inspect the agenda and one slide from each chapter at both `16:9` and `4:3`. Confirm:

- No agenda text crosses a card boundary.
- No generic core-insight fallback sentence appears.
- Chapter markers read `01`, `02`, `03`, and `04` in the expected groups.
- The chapter marker does not overlap titles, kickers, charts, images, or the Citi logo.
- Cover, agenda, and closing slides have no chapter marker.

- [ ] **Step 5: Commit the reference and final verification updates**

```bash
git add backend/app/templates/presentation-framework.html backend/tests/test_api.py
git commit -m "docs: align presentation framework with agenda chapters"
```

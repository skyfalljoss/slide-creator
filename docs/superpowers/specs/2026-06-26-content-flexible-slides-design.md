# Content-Flexible Slides: Richer Content, Removed Truncation, Callout + Context Fields

**Date:** 2026-06-26
**Status:** Approved design — ready for implementation planning

## Problem

Slide content is too thin for both the presenter and the audience. Current constraints:

1. **Hard bullet truncation:** `MAX_BULLETS = 5` in the prompt, plus `bullets[:5]`/`bullets[:3]` in PPTX rendering — the model produces more content but it's silently dropped.
2. **Shallow bullets:** Each bullet is 1-2 sentences with one data point. They lack supporting evidence, examples, comparisons, and the depth needed to stand alone as a spoken narrative.
3. **Generic speaker notes:** Notes are 2-4 sentences that rephrase the bullets. They don't provide context, data sources, delivery guidance, or audience Q&A prep.
4. **No highlighted takeaway:** Every slide has equal visual weight for every point. There's no "headline insight" that grabs attention.
5. **No presenter prep area:** Context like methodology, market background, or data sourcing has nowhere to live without cluttering the slide.

## Design

### 1. New Schema Fields

Add two optional fields to `SlideData`:

- **`callout: str | None`** — A single highlighted key takeaway sentence per content slide. Rendered as a visual accent box (colored border/background, slightly larger/italic text) below the title and above the content area. The one thing the audience should remember.
- **`narrative_context: str | None`** — Background context for the presenter: market conditions, methodology notes, data provenance, strategic rationale. NOT rendered on the slide. Stored for presenter reference via the notes pane.

Both default to `None`. Old decks render identically.

### 2. Richer Bullets (Remove Hard Limits)

**Prompt level:** Remove `MAX_BULLETS = 5`. Replace with content-driven guidance:
> "Use 3-12 bullets per slide. Let the topic's depth determine the count — a simple point may need 3, a complex argument may need 10-12. Each bullet should be 2-4 sentences with supporting evidence, concrete examples, and data points. Each bullet must be a complete, self-contained insight the presenter could read aloud."

**Quality rules update:**
> "Each bullet 2-4 sentences — include supporting evidence, examples, and data. A bullet about a market trend should cite the timeframe and magnitude; a bullet about a recommendation should state the expected impact. Ban filler like 'improve efficiency' without quantification."

### 3. Expanded Speaker Notes

Notes expand from 2-4 sentences to 5-10 sentences covering:
1. **Context:** What led to this slide, how it fits in the story
2. **Key message:** The single message to convey
3. **Data sources:** Where numbers come from, methodology notes
4. **Anticipated questions:** 1-2 likely audience questions with suggested responses
5. **Delivery guidance:** Pace, emphasis, tone cues

**Quality rules update:**
> "Notes should be 5-10 sentences. Structure: context sentence, key message, data sources (2-3 sentences), anticipated audience questions (1-2 with answers), delivery note."

### 4. Callout Rules (New)

Every content slide should have a `callout` field set to the single most important takeaway — a sentence that works as a headline or pull-quote for that slide.

**Prompt addition:**
> "For each content slide, provide a `callout` — one sentence that captures the single most important takeaway. This should work as a headline or pull-quote. Set to null for title, section_divider, and thank-you slides."

### 5. PPTX Rendering Changes

#### Bullet truncation removal

Remove all `bullets[:N]` slicing across layout handlers:

| Layout/Variant | Current | New |
|---|---|---|
| `title` | `bullets[:3]` as secondary text | ALL bullets (below title) |
| `content` + standard | `bullets[:5]` | ALL bullets, modern panel auto-sizes |
| `content` + split_image | `bullets[:4]` | ALL bullets in narrative panel (scroll-friendly) |
| `content` + closing | `bullets[:3]` | ALL bullets below closing title |
| `content` + process | `bullets[:4]` as steps | First 4 as steps, remaining as supporting text below |
| `content` + three_points | `bullets[:3]` as cards | First 3 as card items, remaining as detail list below cards |
| `content` + big_statement | `bullets[0]` as subtitle | ALL bullets as body text below statement |
| `content` + big_stat | `bullets[0]` as label | ALL bullets as supporting detail below stat |
| `next_steps` | `bullets[:3]` as cards, `bullets[3:]` as timeline | No slicing — all bullets distributed |
| `executive_summary` | splits `(len+1)//2` into 2 columns | Already uses all bullets — unchanged |

#### Callout rendering

Add `add_callout_box()` to `PptxCanvas`:
- Position: below title, above content area
- Style: accent-colored left border (4pt), light accent fill, italic text in 14pt
- Dimensions: full content width, auto-height (single line or wraps)
- Only rendered when `slide.callout is not None`

#### Narrative context rendering

No slide rendering. Written to `slide.notes_slide.notes_text_frame.text` appended after the main notes (separated by a `---` divider) so presenters can find it in Presenter View.

### 6. Template Changes

#### `app/prompts/rules.py`

- Expand `BULLET_QUALITY_RULES`: allow 2-4 sentences, supporting evidence/examples/data, ban filler
- Expand `NOTES_QUALITY_RULES`: 5-10 sentences with context, data sources, audience Q&A, delivery guidance
- Add `CALLOUT_QUALITY_RULES`: one-sentence key takeaway per content slide
- Add `NARRATIVE_CONTEXT_RULES`: optional context field for presenter background

#### `app/prompts/generation.py`

- Remove `max_bullets` variable
- Replace with content-driven count guidance
- Add callout rules reference
- Add narrative_context rules reference

#### `app/prompts/script.py`

Same changes as generation.py.

#### `app/prompts/refine.py`

Same changes, plus preserve existing callout/narrative_context when not explicitly changed.

### 7. Code Changes

| File | Changes |
|------|---------|
| `app/models/schemas.py` | Add `callout: str \| None = None`, `narrative_context: str \| None = None` |
| `app/prompts/rules.py` | Expand BULLET/NOTES quality rules; add CALLOUT/NARRATIVE_CONTEXT rules |
| `app/prompts/generation.py` | Remove max_bullets, add callout/context rules |
| `app/prompts/script.py` | Same |
| `app/prompts/refine.py` | Same, with preservation logic |
| `app/services/generation/gemini_api.py` | Remove MAX_BULLETS, remove truncation in response parser |
| `app/services/generation/gemini.py` | Update `_mock_slides` for richer mock content |
| `app/services/presentation/pptx_canvas.py` | Add `add_callout_box()` |
| `app/services/presentation/pptx_layouts.py` | Remove all `bullets[:N]`; integrate callout rendering |
| `app/services/presentation/pptx_engine.py` | Pass callout + narrative_context to layout handlers |
| `tests/` | Update tests for richer bullets, no truncation, new fields |

### 8. Error Handling / Edge Cases

- **callout is None:** Layouts skip callout rendering (no empty boxes). Existing behavior.
- **narrative_context is None:** Notes pane unaffected. Existing behavior.
- **Very long bullets (10+ sentences):** PPTX auto-sizing shrinks font. Acceptable.
- **Refine changes callout:** Model preserves callout from current slide when not explicitly changed by the instruction (same preservation pattern as kicker/subtitle).
- **Refine doesn't set narrative_context:** Same preservation logic. If current slide has narrative_context and refine doesn't override, it's kept.

### 9. Backward Compatibility

- Old sessions loaded from storage have slides without `callout`/`narrative_context` → defaults to `None` → rendered identically
- Export of old decks works with no changes
- All existing tests pass with updated expectations
- No database or external storage schema changes

# Content Quality & Flexible Slide Count

**Date:** 2026-06-25
**Status:** Approved design — ready for implementation planning

## Problem

Two issues with the current SlideForge slide generation:

1. **Hardcoded slide count:** `deck_type` (`sales_9`/`internal_6`) enforces strict targets (9 or 6 slides ±3). The AI must produce exactly the right number or the response is rejected. This doesn't match how content actually works — some briefs need 4 slides, some need 14.

2. **Generic content:** Slide bullets are too short and vague ("improve efficiency"), image prompts are generic business scenes unrelated to the specific slide topic, titles read like section labels, and speaker notes lack substance.

## Design

### 1. Flexible Slide Count

**`deck_type` becomes optional hint.** The `GenerateRequest.deck_type` field changes from `Literal["sales_9", "internal_6"]` to `str | None = None`. When provided, it's passed as a loose hint in the prompt ("The user mentioned this deck type, but adjust to the content's actual structure"). When absent, the AI decides purely on content.

**Server-side enforcement removed.** `parse_slides_response()` no longer validates count against `SLIDE_COUNTS`. Instead it uses a wide acceptable range (3-20 for non-script, 3-20 for script). The prompt tells the AI: "Create between 4 and 15 slides depending on content depth." This is guidance, not validation.

**`_max_slide_count()` defaults to 20** when `deck_type` is `None`, keeping `normalize_deck()`'s Thank-You-appending logic functional.

### 2. Content Quality — Prompt Rewrites

All quality changes live in `app/prompts/` — no pipeline code changes needed. The three prompt templates (generation, script, refine) get updated style rules.

**New style rules for bullets:**
Each bullet should be 1-2 sentences — specific enough to stand alone as a meaningful insight, short enough to scan in seconds. Include a concrete number, %, dollar figure, or timeframe. Ban generic phrases like "improve efficiency". Example guidance:

> ❌ "Improve efficiency" (too vague, too short)
> ❌ Full-paragraph bullet (death by PowerPoint)
> ✓ "Reduce report generation time by 60% through automated compliance checks" (specific, quantified, scannable)

**New style rules for titles:**
State a concrete takeaway, not a label. Compare:
> ❌ "Process Improvement" (label)
> ✓ "Automation unlocks faster reporting with stronger controls" (takeaway)

**New style rules for image prompts:**
Must directly illustrate this specific slide's topic, not a generic business scene. Compare:
> ❌ "corporate business meeting" (generic)
> ✓ "solar farm panels at sunset clean energy installation" (specific to a slide about solar financing)

**New style rules for notes:**
2-4 sentences explaining the significance, context, and talking points. Not just a rephrased bullet.

**New style rules for kickers:**
Vary across the deck — don't repeat the same 2-3 labels. Each slide gets a distinct angle.

### 3. Rules File Structure

- `app/prompts/rules.py` — Image rules tightened, new quality guidance rules added
- `app/prompts/generation.py` — Style rules section replaced with quality-focused version
- `app/prompts/script.py` — Same treatment
- `app/prompts/refine.py` — Same treatment

### 4. Backward Compatibility

- `deck_type` remains in `GenerateRequest` as an optional field (default `None`)
- Existing API clients that send `deck_type` continue to work — it's silently treated as a hint
- `SLIDE_COUNTS` and `SLIDE_COUNT_TOLERANCE` module-level constants remain for `export.py` and `generate.py` imports (updated to handle None)
- `normalize_deck()` unchanged — still appends Thank You slide

## Files Changed

| File | Change |
|------|--------|
| `app/models/schemas.py` | `deck_type` from `Literal` to `str \| None = None` |
| `app/prompts/rules.py` | Tightened image rules, added quality guidance constants |
| `app/prompts/generation.py` | Replaced style rules with quality-focused version; flexible slide count wording |
| `app/prompts/script.py` | Same quality-focused rewrites |
| `app/prompts/refine.py` | Same quality-focused rewrites |
| `app/services/generation/gemini_api.py` | Removed strict count enforcement; wide range in `parse_slides_response` |
| `app/services/generation/gemini.py` | Updated to handle optional deck_type |
| `app/routers/generate.py` | Updated `_max_slide_count()` for optional deck_type |
| `app/routers/export.py` | Handle missing deck_type key gracefully |
| `tests/test_gemini_api.py` | Updated for new count validation logic |
| `tests/test_api.py` | Updated for optional deck_type |
| `tests/test_pptx_engine.py` | If affected by mock slide data changes |

## Not Changing

- `deck_normalizer.py` — unchanged (handles any slide count)
- Session store, DLP, audit, image resolution — unchanged
- PPTX engine/layouts — unchanged
- Frontend — no changes needed (API contract is backward compatible)

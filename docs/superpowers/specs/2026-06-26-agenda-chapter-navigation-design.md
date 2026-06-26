# Agenda Chapter Navigation Design

## Goal

Make the presentation structure immediately understandable by replacing the current `Today's Discussion` slide with a professional `Presentation Agenda` and carrying its chapter numbers through every related content slide.

## Approved Visual Direction

Use the selected Option A treatment:

- Title the overview slide `Presentation Agenda`.
- Present up to four chapters in a balanced 2x2 card grid.
- Use large, pale `01` through `04` numbers, a concise chapter title, and a short supporting description in each card.
- Carry the active chapter number and chapter label into the header of every related content slide.
- Repeat a chapter number across all slides belonging to that chapter; do not use the chapter marker as a slide counter.
- Exclude the cover, agenda, and final closing slide from chapter markers.

## Content Rules

Agenda descriptions must be specific to the deck. The generic sentence `The context and core insight for the discussion.` must not appear.

For each agenda card:

- Chapter title: preferably 2-5 words, capped at 42 characters.
- Description: one sentence fragment, preferably 8-14 words, capped at 90 characters.
- Description source priority: chapter-level summary from generation, then the first related slide's callout, subtitle, or first bullet.
- If no useful source exists, use a concise neutral fallback such as `Key context, evidence, and decisions for this chapter.`

Long generated content will be normalized before rendering. The renderer will also use bounded text boxes and length-aware font sizing so text cannot extend beyond its agenda card.

## Chapter Data Model

Add optional chapter metadata to slide data:

- `chapter_number`: integer from 1 through 4.
- `chapter_title`: concise label matching an agenda card.

Expose the fields in the backend schemas and frontend `SlideData` type so generation, refinement, saved decks, preview, and export preserve the same chapter assignment.

Generation prompts will require each non-cover, non-agenda, non-closing slide to identify its agenda chapter. The generated agenda must contain the same ordered chapter titles.

## Normalization

The deck normalizer remains the source of truth:

1. Reuse one existing agenda, outline, overview, roadmap, or discussion slide when present; otherwise insert one after the cover.
2. Normalize its title to `Presentation Agenda` and remove duplicate overview slides.
3. Build up to four ordered chapters from valid generated chapter metadata.
4. For legacy or incomplete decks, assign content slides to contiguous chapters in presentation order and derive chapter titles from the first slide in each group.
5. Normalize every content slide to a valid chapter number and the matching agenda title.
6. Keep chapter assignments stable when slide indexes are refreshed.

The contiguous fallback is deterministic and avoids unreliable keyword classification. Generated decks receive semantic chapter assignments from the prompt; older decks still receive predictable navigation.

## PPTX Rendering

The agenda renderer will use fixed card geometry with separate bounded regions for number, title, and description. Content must fit within card bounds at both supported aspect ratios.

Chapter navigation will be rendered independently of layout-specific title code. This ensures markers appear on:

- Standard content and card slides.
- Big statement and big statistic slides.
- Split-image, quote, process, comparison, and before/after slides.
- Chart and block-driven slides.

The marker will use the active theme for contrast. Light slides use a Citi red number marker with a navy chapter label; dark slides use a high-contrast equivalent. Layout-specific renderers may adjust placement, but they may not omit the marker.

## Prompt And Template Updates

Update generation and refinement instructions to use `Presentation Agenda`, concise agenda copy, and chapter metadata. Update the HTML presentation reference so generated visual guidance matches the PPTX output.

## Testing

Add regression coverage for:

- Normalizing the overview title to `Presentation Agenda` without duplication.
- Removing the generic fallback sentence.
- Trimming or sizing long agenda descriptions within card bounds.
- Preserving generated chapter assignments.
- Deterministic fallback chapter assignment for legacy decks.
- Rendering repeated chapter numbers across multiple related slides.
- Rendering chapter markers on every special variant and chart route.
- Omitting markers from cover, agenda, and closing slides.
- Keeping agenda text boxes within their corresponding card geometry.

Run backend Ruff and the full pytest suite, then frontend tests and production build because the shared slide type changes.

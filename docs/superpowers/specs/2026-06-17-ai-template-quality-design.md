# AI Template Quality Design

## Goal

Improve SlideForge output quality so generated decks use the user's Citi investment-banking sample format as a visual reference, produce stronger AI-written slide content, render more attractive slides, and keep charts 100% grounded in uploaded CSV/XLSX data.

## Current State

The backend generation path currently uses a local mock `GeminiService` that returns fixed sample slides regardless of the user prompt. Refinement also uses mock behavior by prefixing the title and appending text to bullets. PPTX export renders a basic title/content deck using `python-pptx` with simple bullet placement, optional chart rendering, a Citi logo/text fallback, and a footer.

The backend includes `backend/app/templates/Citi PPTW Format - Sample Investment Banking Presentation.pptx`. This is a good location because the file is a backend rendering/style asset. Inspection shows the sample deck has a 16:9 wide banker-style canvas, Arial typography, dark title text, Citi/navy accents, section dividers, dense two-column layouts, source notes, and footer section labels. Direct `python-pptx` slide iteration failed on the sample because of an unusual slide relationship structure, so the implementation must not depend on directly filling that file as the primary path.

## Approved Direction

Use the sample PPTX as a visual reference, not as a brittle direct template dependency. Recreate the relevant format programmatically with `python-pptx`:

- Match the sample deck canvas at approximately 17.78 by 10 inches.
- Use Arial, dark title text, Citi/navy accents, light gray panels, and subtle separators.
- Render title, section divider, executive summary, content, chart, and next-step layouts with deliberate visual hierarchy.
- Avoid raw bullet dumps by using left narrative/right visual composition, metric cards, callout panels, process arrows, chart areas, source notes, and section/footer labels.
- Keep the existing local provider for tests and development fallback.

## AI Provider

Add a Gemini Developer API provider selected with environment configuration:

- `AI_PROVIDER=gemini`
- `GEMINI_API_KEY=<developer-api-key>`
- `GEMINI_MODEL=<model-name>`

If `AI_PROVIDER=gemini` is configured without `GEMINI_API_KEY`, generation and refinement fail with a clear setup error. `AI_PROVIDER=local` remains supported for tests, offline development, and fallback demos.

The Gemini provider returns strict structured JSON. The backend validates that JSON before storing the session. Gemini output includes:

- fixed slide count based on deck type
- slide index
- title
- concise bullets
- speaker notes
- layout intent
- `visual_direction`
- optional chart recommendation metadata

The prompt must instruct Gemini not to invent chart data, not to invent client-confidential details, and not to return prose outside the JSON response.

## Chart Correctness

Charts must be deterministic and auditable.

Allowed chart source:

- Uploaded CSV/XLSX only.

Disallowed chart sources:

- AI-generated values.
- AI-inferred values.
- Numeric facts extracted from free-form prompt text.
- Placeholder/demo values when no upload exists.

Gemini may recommend the chart type and explain which uploaded columns would support the narrative. The backend alone extracts chart categories, series, values, and labels from uploaded rows. If Gemini recommends unavailable columns or an invalid chart type for the data, the backend rejects the recommendation and renders a non-chart visual instead.

Every chart slide should include chart audit metadata:

- uploaded source filename
- category column
- value columns
- row count used
- selected chart type
- whether Gemini's chart recommendation was accepted or rejected
- rejection reason when applicable

Every exported chart slide should include a small source note such as `Source: uploaded_file.xlsx; columns: Quarter, Revenue`.

## Generation Flow

1. User enters a prompt and optionally uploads CSV/XLSX data.
2. Backend DLP scans the prompt.
3. Backend parses uploaded rows and creates a compact upload summary for Gemini.
4. Gemini receives the prompt, deck type, upload summary, strict JSON schema instructions, chart correctness rules, and style guidance inspired by the sample deck.
5. Gemini returns structured slide JSON with narrative content, speaker notes, visual direction, and optional chart recommendation metadata only.
6. Backend validates slide count, indexes, content shape, layout values, visual direction, and chart recommendations.
7. Backend builds chart data only from uploaded rows when a chart recommendation is valid.
8. Backend drops invalid chart recommendations and adds a no-chart visual direction instead.
9. Backend DLP scans generated slide content before creating the session.
10. Frontend stores and previews the validated slides.

## Refinement Flow

Refinement should use Gemini when `AI_PROVIDER=gemini`:

- DLP scan the user instruction.
- Load the current session and selected slide.
- Send only the selected slide, deck context, and refinement instruction to Gemini.
- Preserve slide index and existing chart data unless a valid uploaded-file-backed chart recommendation is explicitly made and accepted.
- Validate returned slide content and `visual_direction`.
- DLP scan the refined slide.
- Update the session and clear stale exports.

When `AI_PROVIDER=local`, refinement should remain deterministic and test-friendly.

## Data Model

Extend `SlideData` with optional metadata:

- `visual_direction: str | None`
- `chart_recommendation: ChartRecommendation | None`
- `chart_audit: ChartAudit | None`

`chart_data` remains the only field used to render actual chart values. `chart_recommendation` explains what Gemini suggested. `chart_audit` explains what the backend accepted and rendered.

Frontend types mirror the backend schema. The preview page shows `visual_direction` only in a collapsible `Design direction` panel so the main preview stays clean.

## PPTX Rendering

The PPTX renderer should become layout-aware instead of only checking the slide index and chart presence.

Renderer requirements:

- Set slide size to approximately 17.78 by 10 inches to match the sample format.
- Use programmatic layouts inspired by the sample deck.
- Render title slides with confidentiality label, strong headline, subtitle/details, and date.
- Render section divider slides when layout intent indicates a divider.
- Render content slides with a large title, left narrative, and right visual panel.
- Render chart slides with left insight bullets and right deterministic chart region.
- Render source notes for chart slides.
- Render next-step slides with action cards or process blocks.
- Render footer text with page number and section label.
- Continue writing speaker notes into PPTX notes.
- Keep logo handling via configured `CITI_LOGO_PATH`, with styled text fallback.

The direct sample PPTX may be explored as a best-effort style source, but implementation quality cannot depend on direct template filling because the file is not reliably iterable via `python-pptx`.

## Frontend Preview

The preview should look closer to an actual slide instead of a raw text card.

Preview requirements:

- Render a slide-like 16:9 panel.
- Show title hierarchy, section/footer accents, bullet groups, and chart/source indicators.
- Show metric/callout/process visual treatments based on `visual_direction` when no valid chart exists.
- Show chart source and validity metadata when `chart_audit` exists.
- Keep `Design direction` collapsed by default.
- Preserve existing refine buttons and route flow.

## Error Handling

Clear error cases:

- Missing Gemini API key when `AI_PROVIDER=gemini`.
- Gemini returns invalid JSON.
- Gemini returns the wrong slide count.
- Gemini returns unsupported layout intent.
- Gemini recommends chart columns not present in the uploaded file.
- Upload has no usable numeric data for a requested chart.
- DLP rejects prompt, generated content, or refinement output.

Invalid chart recommendations should not fail the whole generation if the rest of the content is valid. Instead, the backend should omit chart data, store an audit rejection reason, and use a non-chart visual layout.

## Testing Strategy

Backend tests should cover:

- Gemini provider requires `GEMINI_API_KEY` when selected.
- Gemini prompt forbids invented chart data.
- Gemini structured JSON parsing and validation.
- Wrong slide count rejection.
- Invalid chart recommendation rejection.
- Uploaded CSV/XLSX remains the only chart data source.
- Chart audit metadata includes source filename, columns, row count, chart type, and acceptance status.
- PPTX renderer creates a non-empty deck with sample-sized canvas, styled text regions, source notes, and speaker notes.
- Local provider still generates deterministic decks for tests.

Frontend tests should cover:

- Preview renders a slide-like panel.
- `Design direction` is collapsed by default and can be expanded.
- Chart audit/source metadata is shown when present.
- Slides without valid chart data show non-chart visual treatment.

## Out Of Scope For This Phase

- Real raster image generation.
- Imagen or other image model integration.
- Chart values extracted from prompt prose.
- User approval workflow for extracted prompt facts.
- Direct dependence on the sample PPTX as a runtime template.
- Database-backed sessions.

## Implementation Notes

- The backend dependency list already includes Google Cloud Vertex packages, but this design uses the Gemini Developer API key path. The implementation should choose the smallest appropriate Gemini client dependency or direct HTTP call.
- `.superpowers/` should be ignored by git if visual brainstorming files remain in the project directory.
- `.gitignore` should unignore backend template PPTX files because the project currently ignores `*.pptx` globally.
- Existing tests assume local mock behavior. Keep local provider behavior stable enough to avoid brittle test rewrites.

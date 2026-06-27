CHART_RULES = """Critical chart rules:
- Uploaded CSV/XLSX is the only allowed chart data source.
- Do not invent chart values, categories, labels, totals, or series.
- If recommending a chart, only reference columns present in the uploaded data summary.
- If no uploaded data exists, set chart_recommendation to null."""

IMAGE_RULES = """Image prompt rules (image_prompt field):
- Write a short prompt for an AI image generator that illustrates the slide's theme.
- The image MUST be directly related to this specific slide's topic. For a slide about "Solar farm financing", use "solar panels acreage sunset clean energy installation", not a generic "corporate business meeting".
- Describe ONLY a photorealistic photograph or an abstract artwork scene.
- NEVER request text, labels, words, charts, diagrams, infographics, tables, or bullet points (AI image models render these as garbled text).
- Describe a concrete scene, lighting, color palette, and mood. Keep it under 30 words.
- Also provide image_query: 3-6 plain keywords describing a concrete, photographable subject for stock-photo search (e.g. "solar panels rooftop sunset"). No text, charts, or abstract concepts."""

LAYOUTS_LINE = "Allowed layouts: title, executive_summary, content, chart, section_divider, next_steps."

VARIANT_RULES = """Framework variant rules:
- Use presentation-framework.html as the visual reference for native editable PPTX structure.
- Set variant to one of: cover, big_statement, three_points, split_image, big_stat, before_after, comparison_table, process, quote, closing.
- Use cover for the first title slide.
- Add exactly one overview slide immediately after the cover titled "Presentation Agenda", using process variant with 3-4 chapters. Each chapter needs a 2-5 word title and an 8-14 word description. Do not create another agenda, outline, overview, roadmap, or discussion slide.
- Set chapter_number (1-4) and chapter_title on every content slide except the agenda and final closing slide. Related slides must repeat the same chapter metadata.
- Use closing for a separate final slide titled "Thank You"; put concrete next steps on the preceding process/next_steps slide when the deck length allows.
- Create visual rhythm by alternating light slides with darker emphasis slides; big_statement, big_stat, quote, and closing are best for dark-background treatment.
- Use split_image when a narrative slide benefits from a strong right-side visual.
- Use big_stat for one dominant metric; use comparison_table for capability/vendor comparisons; use process for timelines; use quote for a vision/client quote.
- Do not overuse cards. Use three_points/cards only for true pillars, differentiators, or parallel points.
- Always provide bullets as fallback content even when blocks is present."""

COMPONENT_RULES = """Component blocks (blocks field) — think like a UI designer choosing a React component:
For each CONTENT slide, choose the ONE component that best presents the material and return it as a single-item list. Available components:
- {"type":"cards","columns":3,"items":[{"title":"Velocity","body":"One concise sentence.","icon":"speed"}]} — 2-4 feature/pillar/point cards. Each item may set an icon keyword (speed, security, growth, global, process, quality, innovation, client, data).
- {"type":"stat","value":"48%","label":"Reduction in infrastructure costs"} — a single headline metric.
- {"type":"quote","text":"...","author":"Name - Title"} — a pull quote.
- {"type":"table","headers":["Feature","Legacy","New"],"rows":[["Compliance","Manual","Native"]]} — a comparison table.
- {"type":"process","steps":[{"title":"Audit","body":"..."}]} — 2-4 sequential steps.
- {"type":"bullets","items":["..."]} — plain bullet fallback.
Pick the component that matches the content's shape (metrics -> stat, comparisons -> table, sequence -> process, parallel points -> cards).
Set blocks to null for title, executive_summary, section_divider, and chart slides. Always also fill bullets as a fallback."""

SCHEMA_BLOCK = """JSON schema:
{
  "slides": [
    {
      "index": 1,
      "title": "Slide title",
      "kicker": "Short uppercase eyebrow label (2-4 words)",
      "subtitle": "Short supporting line for title and section_divider slides",
      "chapter_number": null,
      "chapter_title": null,
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

TITLE_QUALITY_RULES = """TITLES: Each title must state a specific, concrete takeaway — not a generic section label.
  ❌ "Process Improvement"
  ✓ "Automation unlocks faster reporting with stronger controls" """

BULLET_QUALITY_RULES = """BULLETS: Keep slide bullets concise: one sentence per bullet, generally 14-24 words, with evidence or a concrete action where useful. Ban generic filler like "improve efficiency" without quantification.
  ❌ "Improve efficiency"
  ✓ "Reduce report generation time by 60% through automated compliance checks, saving 120 hours per quarter across the compliance team — equivalent to $48,000 in annual cost avoidance at blended fully-loaded rates."
  A bullet about a market trend should cite timeframe, magnitude, and a concrete example. A bullet about a recommendation should state expected impact and reference supporting evidence. Avoid multi-clause paragraphs and long inline lists."""

NOTES_QUALITY_RULES = """NOTES: 5-10 sentences per slide. Structure your notes as:
1. Context sentence — what led to this slide and how it fits in the overall narrative
2. Key message — the single most important thing the audience should take away
3. Data sources and methodology — 2-3 sentences explaining where the numbers come from, timeframes, methodology notes
4. Anticipated audience questions — 1-2 likely questions with suggested responses
5. Delivery guidance — pace, emphasis, tone cues for the presenter
Do not just rephrase the bullets. The notes should prepare the presenter for the full discussion."""

KICKER_QUALITY_RULES = """KICKERS: Vary the kicker across slides. Each slide gets a distinct 2-4 word angle. Don't repeat the same labels."""

CALLOUT_QUALITY_RULES = """CALLOUT: For every content slide (layout: content), provide a `callout` field with one sentence that captures the single most important takeaway. This should work as a headline or pull-quote — the one thing the audience must remember. Set callout to null for title, section_divider, and thank-you slides."""

NARRATIVE_CONTEXT_RULES = """NARRATIVE_CONTEXT (optional): For complex slides, provide a `narrative_context` field with 2-4 sentences of background context — market conditions, methodology notes, data provenance, strategic rationale. This is stored for presenter reference and does NOT appear on the slide. Set to null for simple slides where bullets and notes already convey full context."""

AUDIENCE_TONES: dict[str, str] = {
    "corporate": "Audience: corporate executives. Use a polished, board-ready, professional tone.",
    "casual": "Audience: a general audience. Use a clear, friendly, plain-language tone.",
    "academic": "Audience: an academic audience. Use a precise, formal, evidence-based tone.",
}


def audience_tone(audience: str) -> str:
    return AUDIENCE_TONES.get(audience, AUDIENCE_TONES["corporate"])

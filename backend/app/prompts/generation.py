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

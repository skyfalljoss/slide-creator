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

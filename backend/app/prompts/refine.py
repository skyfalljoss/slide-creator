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

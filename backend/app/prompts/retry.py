RETRY_PROMPT_TEMPLATE = """The previous response could not be parsed as the required slide JSON.
Parser error: {error}

Return a corrected response now.
Rules:
- Return JSON only.
- Do not use markdown fences.
- Use double quotes for every JSON property name and string.
- Do not include comments, trailing commas, or prose.
- Preserve the requested deck intent and schema.

Bad response excerpt:
{bad_response_excerpt}

Original request:
{original_prompt}"""

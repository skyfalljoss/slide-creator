"""Build clean, text-free image-generation prompts for slide visuals.

AI image generators render garbled, illegible text whenever a prompt asks for
charts, diagrams, infographics, or labeled visuals. This module maps slide
content to curated photorealistic / abstract prompts (no text, no labels, no
diagrams), provides a generic fallback, and runs a sanitizer that strips banned
terms, appends a mandatory no-text suffix, and keeps prompts short.
"""

import re

from app.models.schemas import SlideData

# Mandatory suffix appended to every prompt.
PROMPT_SUFFIX = (
    ", no text, no labels, no diagrams, photorealistic OR abstract art style, "
    "16:9 aspect ratio"
)

# Words that must never appear in an image prompt (they invite garbled text).
_BANNED_PATTERN = re.compile(
    r"\b(?:infographic|chart|diagram|comparison|bullet|slide|table)s?\b",
    flags=re.IGNORECASE,
)

# Maximum total words in the final prompt (simpler prompts render cleaner).
_MAX_WORDS = 60

# Curated, on-theme prompts. Each entry is (keywords, prompt). First match wins.
_THEME_PROMPTS: list[tuple[tuple[str, ...], str]] = [
    (
        ("chatbot", "contact center", "call center", "customer experience",
         "customer service", "customer support", "cx"),
        "Wide-angle photograph of a modern enterprise contact center at dusk, "
        "rows of curved desks with glowing monitors, blue ambient lighting, "
        "no people visible, cinematic depth of field",
    ),
    (
        ("supply chain", "warehouse", "logistics", "inventory", "fulfillment",
         "distribution"),
        "Aerial photograph of an automated warehouse at night, rows of "
        "illuminated shelving, robotic systems visible as streaks of orange "
        "light, blue and white color palette, photorealistic",
    ),
    (
        ("roadmap", "phased", "phase", "timeline", "milestone", "rollout",
         "implementation plan", "next steps", "next step"),
        "Abstract digital visualization of a glowing timeline path through a "
        "dark space, four distinct light nodes connected by luminous arcs, "
        "deep navy background, blue and teal accent colors, cinematic",
    ),
    (
        ("benefit", "value", "roi", "return on investment", "advantage",
         "why citi", "differentiator"),
        "Professional photograph of glass office tower exterior at golden hour, "
        "upward perspective, geometric reflections of sky, blue and gold tones, "
        "sharp and clean",
    ),
    (
        ("opportunity", "market overview", "situation"),
        "Abstract visualization of a neural network expanding outward from a "
        "central point, glowing blue nodes on a deep navy background, high "
        "resolution",
    ),
    (
        ("closing", "call to action", "cta", "conclusion", "thank you",
         "get started", "in summary"),
        "Wide aerial photograph of a modern city skyline at twilight, "
        "reflections in water below, warm and cool light contrast, "
        "cinematic quality",
    ),
]

# Divider slides default to the opportunity / neural-network visual.
_DIVIDER_PROMPT = (
    "Abstract visualization of a neural network expanding outward from a "
    "central point, glowing blue nodes on a deep navy background, high resolution"
)


def sanitize_prompt(prompt: str) -> str:
    """Strip banned terms, append the no-text suffix, and cap the word count."""
    cleaned = _BANNED_PATTERN.sub("", prompt)
    # Collapse whitespace and tidy up stray/duplicated commas left by removals.
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*,(?:\s*,)+", ",", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = cleaned.strip().strip(",").strip()

    suffix_word_count = len(PROMPT_SUFFIX.split())
    max_body_words = _MAX_WORDS - suffix_word_count - 1
    body_words = cleaned.split()
    if len(body_words) > max_body_words:
        body_words = body_words[:max_body_words]
    body = " ".join(body_words).rstrip(",").strip()
    return f"{body}{PROMPT_SUFFIX}"


def _match_theme(haystack: str) -> str | None:
    for keywords, prompt in _THEME_PROMPTS:
        if any(keyword in haystack for keyword in keywords):
            return prompt
    return None


_STOPWORDS = frozenset(
    {"the", "a", "an", "and", "or", "of", "to", "for", "with", "our", "your",
     "why", "in", "on", "is", "are", "we", "us"}
)


def build_stock_query(slide: SlideData) -> str:
    """Return a short keyword query for stock-photo search (no AI suffix).

    Prefers a Gemini-authored ``image_query`` (concrete, photographable keywords);
    falls back to the slide title. Either way, banned terms and stopwords are
    stripped and the query is capped to a few words.
    """
    source = (getattr(slide, "image_query", None) or "").strip() or (slide.title or "")
    raw = _BANNED_PATTERN.sub("", source)
    words = [w for w in re.findall(r"[A-Za-z]+", raw) if w.lower() not in _STOPWORDS]
    query = " ".join(words[:6]).strip()
    return query or "corporate business abstract"


def build_image_prompt(slide: SlideData) -> str:
    """Return a clean, text-free image prompt for ``slide``.

    Preference order:
    1. A Gemini-authored ``image_prompt`` on the slide (sanitized).
    2. A curated theme prompt matched on the slide title/bullets.
    3. A generic photorealistic fallback derived from the title.

    The result is always sanitized: banned terms removed, mandatory no-text suffix
    appended, and word count capped. ``visual_direction`` is intentionally never
    used, since it carries layout/diagram instructions.
    """
    authored = (getattr(slide, "image_prompt", None) or "").strip()
    if authored:
        return sanitize_prompt(authored)

    if getattr(slide, "layout", "") == "section_divider":
        base = _DIVIDER_PROMPT
    else:
        haystack = " ".join([slide.title, *slide.bullets]).lower()
        base = _match_theme(haystack)
        if base is None:
            title = slide.title.strip() or "a modern corporate concept"
            base = (
                f"Professional photograph representing {title}, modern corporate "
                "environment, blue and navy tones, cinematic lighting, sharp and clean"
            )
    return sanitize_prompt(base)

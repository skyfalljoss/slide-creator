"""Render Font Awesome (free, solid) glyphs to colored PNGs for embedding in PPTX.

We rasterize the glyph to a transparent PNG and insert it as a picture, so the
icon renders identically in PowerPoint and Keynote without the viewer needing the
Font Awesome font installed. Results are cached by (glyph, color, size).
"""

import io
import logging
from pathlib import Path

FA_FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fontawesome" / "fa-solid-900.ttf"
logger = logging.getLogger(__name__)

# Keyword groups -> Font Awesome 6 (solid) glyph. First match wins.
_KEYWORD_GLYPHS: list[tuple[tuple[str, ...], str]] = [
    (("speed", "velocity", "fast", "performance", "agile", "efficiency", "accelerate"), "\uf0e7"),  # bolt
    (("security", "secure", "compliance", "trust", "protect", "risk", "privacy", "governance"), "\uf3ed"),  # shield-halved
    (("growth", "grow", "increase", "expand", "revenue", "value", "roi", "return", "scale"), "\uf3a0"),  # arrow-trend-up
    (("global", "network", "reach", "connect", "integration", "ecosystem", "api", "market", "worldwide"), "\uf0ac"),  # globe
    (("process", "system", "automation", "operations", "workflow", "engine", "infrastructure"), "\uf085"),  # gears
    (("quality", "excellence", "premium", "award", "leader", "best", "rating"), "\uf005"),  # star
    (("innovation", "idea", "insight", "vision", "future", "strategy", "opportunity"), "\uf0eb"),  # lightbulb
    (("client", "customer", "people", "team", "partner", "relationship", "service", "audience"), "\uf0c0"),  # users
    (("chart", "financial", "metrics", "analysis", "results", "data", "analytics"), "\uf201"),  # chart-line
    (("cloud", "platform", "technology", "digital", "storage", "database"), "\uf1c0"),  # database
    (("next", "step", "action", "timeline", "plan", "roadmap", "phase", "deliver"), "\uf061"),  # arrow-right
    (("goal", "objective", "target", "focus", "mission"), "\uf140"),  # bullseye
]

_DEFAULT_GLYPH = "\uf058"  # circle-check

_font_cache: dict[int, object] = {}
_png_cache: dict[tuple[str, str, int], bytes] = {}


def glyph_for(keyword: str | None) -> str:
    text = (keyword or "").lower()
    if text:
        for words, glyph in _KEYWORD_GLYPHS:
            if any(w in text for w in words):
                return glyph
    return _DEFAULT_GLYPH


def _load_font(size_px: int):
    if not FA_FONT_PATH.exists():
        return None
    if size_px not in _font_cache:
        try:
            from PIL import ImageFont

            _font_cache[size_px] = ImageFont.truetype(str(FA_FONT_PATH), size_px)
        except Exception:
            logger.debug("Failed to load Font Awesome font", exc_info=True)
            _font_cache[size_px] = None
    return _font_cache[size_px]


def render_icon_png(keyword: str | None, color_hex: str, px: int = 160) -> bytes | None:
    """Return PNG bytes of the keyword's FA glyph in ``color_hex`` (e.g. 'EE2A24')."""
    glyph = glyph_for(keyword)
    color_hex = (color_hex or "000000").lstrip("#")
    key = (glyph, color_hex, px)
    if key in _png_cache:
        return _png_cache[key]
    font = _load_font(int(px * 0.74))
    if font is None:
        return None
    try:
        from PIL import Image, ImageDraw

        r = int(color_hex[0:2], 16)
        g = int(color_hex[2:4], 16)
        b = int(color_hex[4:6], 16)
        img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), glyph, font=font)
        gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (px - gw) / 2 - bbox[0]
        y = (px - gh) / 2 - bbox[1]
        draw.text((x, y), glyph, font=font, fill=(r, g, b, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        _png_cache[key] = data
        return data
    except Exception:
        logger.warning("Icon render failed", exc_info=True)
        return None

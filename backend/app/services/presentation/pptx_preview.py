import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.models.schemas import SlideData, SlidePreviewResponse
from app.services.generation.deck_normalizer import normalize_deck
from app.services.generation.gemini_api import SLIDE_COUNTS, SLIDE_COUNT_TOLERANCE
from app.services.presentation.pptx_engine import PptxEngine
from app.services.presentation.pptx_layout import CANVAS_DIMS
from app.services.presentation.pptx_text import clean_inline_text
from app.services.presentation.pptx_theme import resolve_theme


class PreviewRendererUnavailable(RuntimeError):
    """Raised when the runtime cannot render PPTX previews to images."""


class PptxPreviewService:
    def __init__(self, *, cache_dir: str | Path | None = None, soffice_path: str | None = None) -> None:
        self.cache_dir = Path(cache_dir or ".data/previews")
        self.soffice_path = soffice_path or os.environ.get("SOFFICE_PATH") or "soffice"

    def render_deck_slide(
        self,
        *,
        deck_id: str,
        slides: list[SlideData],
        deck_type: str,
        theme: str,
        aspect_ratio: str,
        slide_index: int,
        updated_at: str | None = None,
    ) -> SlidePreviewResponse:
        normalized = self._normalize_slides(slides, deck_type)
        if slide_index < 1 or slide_index > len(normalized):
            raise IndexError(f"Slide index {slide_index} is not available")

        key = self._cache_key(normalized, theme, aspect_ratio, slide_index)
        cached = self._read_cache(key)
        if cached is None:
            slide = normalized[slide_index - 1]
            soffice = self._find_soffice()
            if soffice:
                pptx_bytes = self._render_single_slide_pptx(slide, theme=theme, aspect_ratio=aspect_ratio)
                try:
                    cached = self._convert_pptx_to_png(pptx_bytes, soffice=soffice)
                except PreviewRendererUnavailable:
                    cached = self._render_fallback_preview(slide, theme=theme, aspect_ratio=aspect_ratio)
            else:
                cached = self._render_fallback_preview(slide, theme=theme, aspect_ratio=aspect_ratio)
            self._write_cache(key, cached)

        width, height = self._preview_dimensions(aspect_ratio)
        return SlidePreviewResponse(
            deck_id=deck_id,
            slide_index=slide_index,
            image_b64=base64.b64encode(cached).decode("ascii"),
            width=width,
            height=height,
            updated_at=updated_at,
        )

    def _normalize_slides(self, slides: list[SlideData], deck_type: str) -> list[SlideData]:
        max_count = SLIDE_COUNTS.get(deck_type, len(slides) + 1) + SLIDE_COUNT_TOLERANCE
        return normalize_deck(slides, max_count=max_count)

    def _find_soffice(self) -> str | None:
        found = shutil.which(self.soffice_path)
        if found:
            return found
        for candidate in (
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "/usr/local/bin/soffice",
            "/opt/homebrew/bin/soffice",
        ):
            if Path(candidate).exists():
                return candidate
        return None

    def _render_single_slide_pptx(self, slide: SlideData, *, theme: str, aspect_ratio: str) -> bytes:
        engine = PptxEngine(theme=theme, aspect_ratio=aspect_ratio)
        return engine.render([slide])

    def _convert_pptx_to_png(self, pptx_bytes: bytes, *, soffice: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="slideforge-preview-") as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "slide.pptx"
            output_dir = tmp_path / "out"
            output_dir.mkdir()
            input_path.write_bytes(pptx_bytes)

            result = subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--nologo",
                    "--nofirststartwizard",
                    "--convert-to",
                    "png",
                    "--outdir",
                    str(output_dir),
                    str(input_path),
                ],
                capture_output=True,
                timeout=60,
                check=False,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
                raise PreviewRendererUnavailable(f"PPTX preview renderer failed: {detail or 'conversion failed'}")

            pngs = sorted(output_dir.glob("*.png"))
            if not pngs:
                raise PreviewRendererUnavailable("PPTX preview renderer failed: no PNG output")
            return pngs[0].read_bytes()

    def _render_fallback_preview(self, slide: SlideData, *, theme: str, aspect_ratio: str) -> bytes:
        width, height = self._preview_dimensions(aspect_ratio)
        palette = resolve_theme(theme)
        background = tuple(palette.background or palette.surface)
        accent = tuple(palette.accent)
        text = tuple(palette.text)
        muted = tuple(palette.muted)
        panel_bg = tuple(palette.panel_bg)
        border = tuple(palette.panel_border)

        image = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width, 16), fill=accent)
        draw.rounded_rectangle((64, 72, width - 64, height - 64), radius=42, fill=panel_bg, outline=border, width=3)

        title_font = self._load_font(64)
        subtitle_font = self._load_font(30)
        body_font = self._load_font(28)
        small_font = self._load_font(22)
        chip_font = self._load_font(24)

        left = 110
        top = 122
        chapter_number = getattr(slide, "chapter_number", None)
        chapter_title = clean_inline_text(getattr(slide, "chapter_title", ""))
        if chapter_number is not None and chapter_title:
            badge_x, badge_y = left, top
            draw.rounded_rectangle((badge_x, badge_y, badge_x + 92, badge_y + 56), radius=28, fill=accent)
            self._draw_centered_text(draw, f"{chapter_number:02d}", badge_x, badge_y + 3, 92, 48, chip_font, (255, 255, 255))
            draw.text((badge_x + 112, badge_y + 9), chapter_title.upper(), font=small_font, fill=text)
            top += 72

        kicker = clean_inline_text(getattr(slide, "kicker", ""))
        if kicker:
            draw.text((left, top), kicker.upper(), font=small_font, fill=accent)
            top += 40

        title = clean_inline_text(slide.title)
        title_box = self._wrap_text(draw, title, title_font, width - left * 2 - 40)
        draw.multiline_text((left, top), title_box, font=title_font, fill=text, spacing=10)
        top += self._text_height(draw, title_box, title_font, spacing=10) + 18

        subtitle = clean_inline_text(getattr(slide, "subtitle", ""))
        if subtitle:
            subtitle_box = self._wrap_text(draw, subtitle, subtitle_font, width - left * 2 - 120)
            draw.multiline_text((left, top), subtitle_box, font=subtitle_font, fill=muted, spacing=8)
            top += self._text_height(draw, subtitle_box, subtitle_font, spacing=8) + 24

        content_left = left
        content_top = top
        content_width = width - left * 2 - 40
        if slide.chart_data and slide.chart_data.series:
            self._draw_chart_preview(draw, slide, content_left, content_top, content_width, height - content_top - 110, body_font, small_font, text, muted, accent, border)
        elif getattr(slide, "image_b64", None):
            self._draw_image_preview(image, slide.image_b64, content_left, content_top, content_width, height - content_top - 110)
        elif slide.bullets:
            self._draw_bullet_preview(draw, slide.bullets, content_left, content_top, content_width, height - content_top - 110, body_font, muted, accent, border)
        else:
            body = clean_inline_text(getattr(slide, "callout", "") or getattr(slide, "visual_direction", "") or "")
            if body:
                body_box = self._wrap_text(draw, body, body_font, content_width)
                draw.multiline_text((content_left, content_top), body_box, font=body_font, fill=muted, spacing=8)

        return self._png_bytes(image)

    def _cache_key(self, slides: list[SlideData], theme: str, aspect_ratio: str, slide_index: int) -> str:
        payload = {
            "slides": [slide.model_dump(mode="json") for slide in slides],
            "theme": theme,
            "aspect_ratio": aspect_ratio,
            "slide_index": slide_index,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _read_cache(self, key: str) -> bytes | None:
        path = self.cache_dir / f"{key}.png"
        if not path.exists():
            return None
        return path.read_bytes()

    def _write_cache(self, key: str, content: bytes) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{key}.png").write_bytes(content)

    def _preview_dimensions(self, aspect_ratio: str) -> tuple[int, int]:
        width_in, height_in = CANVAS_DIMS.get(aspect_ratio, CANVAS_DIMS["16:9"])
        height = 1080
        width = round((width_in / height_in) * height)
        return width, height

    @staticmethod
    def _load_font(size_px: int):
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                try:
                    return ImageFont.truetype(candidate, size_px)
                except Exception:
                    continue
        return ImageFont.load_default()

    @staticmethod
    def _png_bytes(image: Image.Image) -> bytes:
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def _text_height(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, *, spacing: int = 0) -> int:
        if not text:
            return 0
        boxes = [draw.textbbox((0, 0), line, font=font) for line in text.splitlines() or [text]]
        if not boxes:
            return 0
        heights = [box[3] - box[1] for box in boxes]
        return sum(heights) + spacing * max(len(heights) - 1, 0)

    @staticmethod
    def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
        words = text.split()
        if not words:
            return ""
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return "\n".join(lines)

    @staticmethod
    def _draw_centered_text(draw: ImageDraw.ImageDraw, text: str, left: int, top: int, width: int, height: int, font: ImageFont.ImageFont, fill: tuple[int, int, int]) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        text_w = box[2] - box[0]
        text_h = box[3] - box[1]
        x = left + max(0, (width - text_w) // 2 - box[0])
        y = top + max(0, (height - text_h) // 2 - box[1])
        draw.text((x, y), text, font=font, fill=fill)

    def _draw_bullet_preview(
        self,
        draw: ImageDraw.ImageDraw,
        bullets: list[str],
        left: int,
        top: int,
        width: int,
        height: int,
        body_font: ImageFont.ImageFont,
        muted: tuple[int, int, int],
        accent: tuple[int, int, int],
        border: tuple[int, int, int],
    ) -> None:
        card_w = width
        card_h = min(height, 440)
        draw.rounded_rectangle((left, top, left + card_w, top + card_h), radius=28, fill=(255, 255, 255), outline=border, width=2)
        y = top + 34
        for bullet in bullets[:4]:
            lines = self._wrap_text(draw, clean_inline_text(bullet), body_font, card_w - 120)
            draw.ellipse((left + 28, y + 11, left + 42, y + 25), fill=accent)
            draw.multiline_text((left + 58, y), lines, font=body_font, fill=muted, spacing=8)
            y += self._text_height(draw, lines, body_font, spacing=8) + 28
            if y > top + card_h - 40:
                break

    def _draw_image_preview(self, image: Image.Image, image_b64: str, left: int, top: int, width: int, height: int) -> None:
        import base64 as _base64
        import io

        try:
            raw = _base64.b64decode(image_b64)
            embedded = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            return
        if width <= 0 or height <= 0:
            return
        embedded.thumbnail((width, height))
        x = left + max(0, (width - embedded.width) // 2)
        y = top + max(0, (height - embedded.height) // 2)
        image.paste(embedded, (x, y))

    def _draw_chart_preview(
        self,
        draw: ImageDraw.ImageDraw,
        slide: SlideData,
        left: int,
        top: int,
        width: int,
        height: int,
        body_font: ImageFont.ImageFont,
        small_font: ImageFont.ImageFont,
        text: tuple[int, int, int],
        muted: tuple[int, int, int],
        accent: tuple[int, int, int],
        border: tuple[int, int, int],
    ) -> None:
        card_h = min(height, 500)
        draw.rounded_rectangle((left, top, left + width, top + card_h), radius=28, fill=(255, 255, 255), outline=border, width=2)
        chart_data = slide.chart_data
        draw.text((left + 28, top + 24), clean_inline_text(chart_data.title or slide.title), font=small_font, fill=text)
        series = chart_data.series or []
        values = list(series[0].values or []) if series else []
        if not values:
            return
        max_value = max(float(v) for v in values) or 1.0
        bar_area_top = top + 90
        bar_area_bottom = top + card_h - 60
        bar_area_height = bar_area_bottom - bar_area_top
        bar_width = max(18, min(54, int((width - 100) / max(len(values) * 2, 1))))
        gap = bar_width
        x = left + 38
        for idx, value in enumerate(values[:8]):
            bar_height = int((float(value) / max_value) * bar_area_height)
            draw.rounded_rectangle(
                (x, bar_area_bottom - bar_height, x + bar_width, bar_area_bottom),
                radius=10,
                fill=accent,
            )
            categories = chart_data.categories or []
            label = clean_inline_text(str(categories[idx] if idx < len(categories) else idx + 1))
            draw.text((x, bar_area_bottom + 10), label[:12], font=small_font, fill=muted)
            x += bar_width + gap

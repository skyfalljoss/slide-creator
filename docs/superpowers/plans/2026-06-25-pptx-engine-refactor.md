# PPTX Engine Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `backend/app/services/pptx_engine.py` so `PptxEngine` owns rendering flow and slide layout decisions, while drawing primitives, constants, and routing tables live in focused helpers.

**Architecture:** Preserve current generated PPTX behavior while introducing small modules around the existing engine. `PptxCanvas` will wrap python-pptx shape creation, `LayoutConstants` will centralize common measurements, and `PptxEngine` will delegate low-level drawing through a canvas instance.

**Tech Stack:** FastAPI backend, Python 3.11, python-pptx, Pydantic schemas, pytest, ruff.

---

## File Structure

- Create: `backend/app/services/pptx_layout.py`
  - Owns canvas sizing and reusable layout constants.
- Create: `backend/app/services/pptx_canvas.py`
  - Owns low-level python-pptx shape/text/image helpers.
- Modify: `backend/app/services/pptx_engine.py`
  - Keeps render loop, theme selection, slide routing, and layout-specific `_apply_*` methods.
  - Delegates shape/text/image primitives to `PptxCanvas`.
  - Replaces routing `if/elif` chains with handler registries.
  - Replaces `print()` with logging.
- Modify: `backend/tests/test_pptx_engine.py`
  - Add behavior-lock tests before refactor and keep existing generated-PPTX tests passing.
- Create: `backend/tests/test_pptx_canvas.py`
  - Unit-test canvas primitives independently from full deck rendering.

## Refactor Rules

- Keep public API unchanged: `PptxEngine(template_path=None, theme=None, aspect_ratio="16:9").render(slides) -> bytes`.
- Preserve existing private helper names during migration where practical by adding thin wrappers first. Remove wrappers only after tests are green.
- Do not change generated slide intent, theme colors, or aspect-ratio scaling in this refactor.
- Do not split slide layouts into `pptx_layouts.py` until canvas extraction and routing cleanup are complete; that should be a follow-up refactor.

---

### Task 1: Add Behavior-Lock Tests For Routing, Image Failure, And Theme Restoration

**Files:**
- Modify: `backend/tests/test_pptx_engine.py`

- [ ] **Step 1: Add tests that lock current routing behavior**

Append these tests near the existing variant and image tests in `backend/tests/test_pptx_engine.py`:

```python
def test_content_slide_routes_explicit_variant_before_blocks(monkeypatch):
    engine = PptxEngine()
    calls: list[str] = []

    monkeypatch.setattr(engine, "_apply_big_stat", lambda slide, data: calls.append("big_stat"))
    monkeypatch.setattr(engine, "_apply_blocks", lambda slide, data: calls.append("blocks"))

    data = SlideData(
        index=2,
        title="Revenue",
        bullets=[],
        notes="",
        layout="content",
        variant="big_stat",
        blocks=[{"type": "cards", "items": [{"title": "A"}]}],
    )

    engine._apply_content_slide(object(), data)

    assert calls == ["big_stat"]
```

```python
def test_content_slide_routes_chart_data_before_variant(monkeypatch):
    engine = PptxEngine()
    calls: list[str] = []

    monkeypatch.setattr(engine, "_apply_chart_slide", lambda slide, data: calls.append("chart"))
    monkeypatch.setattr(engine, "_apply_big_stat", lambda slide, data: calls.append("big_stat"))

    data = SlideData(
        index=2,
        title="Revenue",
        bullets=[],
        notes="",
        layout="content",
        variant="big_stat",
        chart_data={
            "type": "bar",
            "title": "Revenue",
            "categories": ["Q1"],
            "series": [{"name": "Revenue", "values": [1.0]}],
        },
    )

    engine._apply_content_slide(object(), data)

    assert calls == ["chart"]
```

- [ ] **Step 2: Add a test that locks split-image dark-state restoration**

Append:

```python
def test_split_image_restores_active_dark_after_render():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    engine = PptxEngine(theme="minimalist")
    engine._active_dark = False
    data = SlideData(
        index=2,
        title="Dark panel",
        subtitle="Subtitle",
        bullets=["One"],
        notes="",
        layout="content",
    )

    engine._apply_split_image(slide, data)

    assert engine._active_dark is False
```

- [ ] **Step 3: Add a test that image decode failures are logged and return `False`**

Add `import logging` at the top of `backend/tests/test_pptx_engine.py`, then append:

```python
def test_add_slide_image_logs_decode_failure(caplog):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    engine = PptxEngine()

    with caplog.at_level(logging.WARNING):
        inserted = engine._add_slide_image(slide, "not valid base64", 0, 0, 1, 1)

    assert inserted is False
    assert "Failed to insert slide image" in caplog.text
```

- [ ] **Step 4: Run the new focused tests and confirm current failure**

Run from `backend/`:

```bash
uv run pytest tests/test_pptx_engine.py::test_content_slide_routes_explicit_variant_before_blocks tests/test_pptx_engine.py::test_content_slide_routes_chart_data_before_variant tests/test_pptx_engine.py::test_split_image_restores_active_dark_after_render tests/test_pptx_engine.py::test_add_slide_image_logs_decode_failure -v
```

Expected: the first three pass, and `test_add_slide_image_logs_decode_failure` fails because the current implementation prints instead of logging.

---

### Task 2: Create Layout Constants And Replace The Highest-Value Magic Numbers

**Files:**
- Create: `backend/app/services/pptx_layout.py`
- Modify: `backend/app/services/pptx_engine.py`
- Modify: `backend/tests/test_pptx_engine.py`

- [ ] **Step 1: Create `LayoutConstants`**

Create `backend/app/services/pptx_layout.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutConstants:
    logical_width: float = 17.7778
    canvas_height: float = 10.0
    left_margin: float = 0.83
    right_margin: float = 0.83
    content_bottom: float = 8.9
    content_gap: float = 0.4
    header_title_width: float = 16.11
    accent_rule_width: float = 1.4
    accent_rule_height: float = 0.05

    @property
    def content_width(self) -> float:
        return self.logical_width - self.left_margin - self.right_margin


LAYOUT = LayoutConstants()
CANVAS_DIMS: dict[str, tuple[float, float]] = {
    "16:9": (LAYOUT.logical_width, LAYOUT.canvas_height),
    "4:3": (13.3333, LAYOUT.canvas_height),
}
```

- [ ] **Step 2: Import constants in `pptx_engine.py`**

Replace the engine-local canvas constants with imported constants:

```python
from app.services.pptx_layout import CANVAS_DIMS, LAYOUT
```

Change the class attributes:

```python
class PptxEngine:
    _LOGICAL_WIDTH = LAYOUT.logical_width
    _CANVAS_DIMS = CANVAS_DIMS
    _DARK_VARIANTS = frozenset({"big_statement", "big_stat", "quote", "closing"})
```

- [ ] **Step 3: Replace repeated margin/header values in `pptx_engine.py`**

Make these mechanical replacements where the value is a layout margin or width:

```python
0.83 -> LAYOUT.left_margin
self._LOGICAL_WIDTH - 1.66 -> LAYOUT.content_width
16.11 -> LAYOUT.header_title_width
8.9 -> LAYOUT.content_bottom
0.4 -> LAYOUT.content_gap
1.4 -> LAYOUT.accent_rule_width
0.05 -> LAYOUT.accent_rule_height
```

Do not replace values that are intentionally local design decisions, such as `9.05` split-panel width, `7.25` image width, or `0.12` quote bar width.

- [ ] **Step 4: Add a constants test**

Append to `backend/tests/test_pptx_engine.py`:

```python
from app.services.pptx_layout import LAYOUT  # noqa: E402


def test_layout_constants_match_default_canvas_width():
    engine = PptxEngine()

    assert LAYOUT.logical_width == pytest.approx(17.7778)
    assert LAYOUT.content_width == pytest.approx(engine._LOGICAL_WIDTH - 1.66)
```

- [ ] **Step 5: Run focused tests**

Run from `backend/`:

```bash
uv run pytest tests/test_pptx_engine.py -v
```

Expected: all `test_pptx_engine.py` tests pass except `test_add_slide_image_logs_decode_failure` if Task 3 has not been completed yet.

---

### Task 3: Extract Drawing Primitives Into `PptxCanvas`

**Files:**
- Create: `backend/app/services/pptx_canvas.py`
- Modify: `backend/app/services/pptx_engine.py`
- Create: `backend/tests/test_pptx_canvas.py`

- [ ] **Step 1: Create the canvas helper**

Create `backend/app/services/pptx_canvas.py`:

```python
import base64
import io
import logging
from collections.abc import Callable

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.slide import Slide
from pptx.util import Inches, Pt

from app.services.icons import render_icon_png
from app.services.pptx_text import add_markdown_paragraph, clean_inline_text, icon_shape
from app.services.pptx_theme import THEMES, WHITE, Theme

logger = logging.getLogger(__name__)


class PptxCanvas:
    def __init__(
        self,
        *,
        canvas_width: float,
        canvas_height: float,
        logical_width: float,
        theme: Theme,
        active_theme: Callable[[], Theme],
        map_color: Callable[[RGBColor], RGBColor],
    ) -> None:
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.logical_width = logical_width
        self.theme = theme
        self._active_theme = active_theme
        self._map_color = map_color
        self._hscale = canvas_width / logical_width

    def ix(self, value: float) -> Inches:
        return Inches(value * self._hscale)

    def iy(self, value: float) -> Inches:
        return Inches(value)

    def add_text(
        self,
        slide: Slide,
        left: float,
        top: float,
        width: float,
        height: float,
        text: str,
        size: int,
        color: RGBColor,
        *,
        bold: bool = False,
        align: PP_ALIGN | None = None,
    ):
        text_box = slide.shapes.add_textbox(self.ix(left), self.iy(top), self.ix(width), self.iy(height))
        text_frame = text_box.text_frame
        self.clear_text_frame(text_frame)
        paragraph = text_frame.paragraphs[0]
        paragraph.text = clean_inline_text(text)
        paragraph.font.name = "Arial"
        paragraph.font.size = Pt(size)
        paragraph.font.bold = bold
        paragraph.font.color.rgb = self._map_color(color)
        if align is not None:
            paragraph.alignment = align
        return text_box

    def add_card_text(self, slide: Slide, x: float, y: float, w: float, h: float, text: str, size: int, color: RGBColor):
        box = slide.shapes.add_textbox(self.ix(x), self.iy(y), self.ix(w), self.iy(h))
        text_frame = box.text_frame
        self.clear_text_frame(text_frame)
        mapped = self._map_color(color)
        for line in text.split("\n"):
            add_markdown_paragraph(text_frame, line, size, "Arial", mapped)
        return box

    def add_bullets_box(self, slide: Slide, bullets: list[str], left: float, top: float, width: float, height: float):
        text_box = slide.shapes.add_textbox(self.ix(left), self.iy(top), self.ix(width), self.iy(height))
        text_frame = text_box.text_frame
        self.clear_text_frame(text_frame)
        text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
        for bullet in bullets:
            add_markdown_paragraph(text_frame, bullet, 18, "Arial", self._map_color(self.theme.text))
        return text_box

    def add_card(self, slide: Slide, x: float, y: float, w: float, h: float, border_color: RGBColor | None = None):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, self.ix(x), self.iy(y), self.ix(w), self.iy(h))
        card.fill.solid()
        card.fill.fore_color.rgb = self._active_theme().surface
        card.line.color.rgb = self._map_color(border_color) if border_color else self._active_theme().border
        card.line.width = Pt(1)
        card.shadow.inherit = False
        try:
            card.adjustments[0] = 0.05
        except Exception:
            logger.debug("Rounded rectangle adjustment is unavailable", exc_info=True)
        return card

    def add_icon_chip(self, slide: Slide, x: float, y: float, size: float = 0.62, icon: str | None = None) -> None:
        chip = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, self.ix(x), self.iy(y), self.iy(size), self.iy(size))
        chip.fill.solid()
        chip.fill.fore_color.rgb = self._active_theme().accent_soft
        chip.line.fill.background()
        chip.shadow.inherit = False
        try:
            chip.adjustments[0] = 0.3
        except Exception:
            logger.debug("Icon chip adjustment is unavailable", exc_info=True)

        inner = size * 0.52
        offset = (size - inner) / 2
        png = render_icon_png(icon, str(self._active_theme().accent))
        if png:
            slide.shapes.add_picture(io.BytesIO(png), self.ix(x + offset), self.iy(y + offset), self.iy(inner), self.iy(inner))
            return

        mark = slide.shapes.add_shape(icon_shape(icon), self.ix(x + offset), self.iy(y + offset), self.iy(inner), self.iy(inner))
        mark.fill.solid()
        mark.fill.fore_color.rgb = self._active_theme().accent
        mark.line.fill.background()
        mark.shadow.inherit = False

    def add_accent_bar(self, slide: Slide, left: float, top: float, width: float, height: float = 0.05) -> None:
        bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            self.ix(left),
            self.iy(top),
            self.ix(width),
            self.iy(height * self.theme.accent_weight),
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = self._active_theme().accent
        bar.line.color.rgb = self._active_theme().accent

    def add_vertical_divider(self, slide: Slide, left: float, top: float, height: float):
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, self.ix(left), self.iy(top), self.ix(0.01), self.iy(height))
        line.fill.solid()
        line.fill.fore_color.rgb = self._active_theme().panel_border
        line.line.color.rgb = self._active_theme().panel_border
        return line

    def add_number_circle(self, slide: Slide, x: float, y: float, number: int, size: float = 0.72) -> None:
        circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, self.ix(x), self.iy(y), self.iy(size), self.iy(size))
        circle.fill.solid()
        circle.fill.fore_color.rgb = self._active_theme().accent
        circle.line.fill.background()
        circle.shadow.inherit = False
        text_frame = circle.text_frame
        text_frame.word_wrap = False
        text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        paragraph = text_frame.paragraphs[0]
        paragraph.text = str(number)
        paragraph.alignment = PP_ALIGN.CENTER
        paragraph.font.name = "Arial"
        paragraph.font.size = Pt(22)
        paragraph.font.bold = True
        paragraph.font.color.rgb = WHITE

    def add_slide_image(self, slide: Slide, image_b64: str | None, left: float, top: float, width: float, height: float) -> bool:
        if not image_b64:
            return False
        try:
            image_data = base64.b64decode(image_b64)
            slide.shapes.add_picture(io.BytesIO(image_data), self.ix(left), self.iy(top), self.ix(width), self.iy(height))
            return True
        except Exception:
            logger.warning("Failed to insert slide image", exc_info=True)
            return False

    def add_scrim(self, slide: Slide, color: RGBColor = RGBColor(0x0A, 0x16, 0x28), opacity: int = 58) -> None:
        rect = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            self.ix(0),
            self.iy(0),
            self.ix(self.logical_width),
            self.iy(self.canvas_height),
        )
        rect.line.fill.background()
        rect.fill.solid()
        rect.fill.fore_color.rgb = color
        srgb = rect.fill.fore_color._xFill.find(qn("a:srgbClr"))
        if srgb is not None:
            alpha = srgb.makeelement(qn("a:alpha"), {"val": str(int(opacity * 1000))})
            srgb.append(alpha)

    @staticmethod
    def clear_text_frame(text_frame) -> None:
        text_frame.clear()
        text_frame.word_wrap = True
        text_frame.margin_left = Inches(0)
        text_frame.margin_right = Inches(0)
        text_frame.margin_top = Inches(0)
        text_frame.margin_bottom = Inches(0)
```

- [ ] **Step 2: Add canvas unit tests**

Create `backend/tests/test_pptx_canvas.py`:

```python
import logging

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.util import Inches, Pt

from app.services.pptx_canvas import PptxCanvas
from app.services.pptx_layout import LAYOUT
from app.services.pptx_theme import THEMES


def _canvas(theme_name: str = "minimalist") -> PptxCanvas:
    theme = THEMES[theme_name]
    return PptxCanvas(
        canvas_width=LAYOUT.logical_width,
        canvas_height=LAYOUT.canvas_height,
        logical_width=LAYOUT.logical_width,
        theme=theme,
        active_theme=lambda: theme,
        map_color=lambda color: color,
    )


def test_canvas_add_text_sets_font_and_margins():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    shape = _canvas().add_text(slide, 1, 1, 4, 1, "**Hello**", 20, THEMES["minimalist"].text, bold=True)

    paragraph = shape.text_frame.paragraphs[0]
    assert paragraph.text == "Hello"
    assert paragraph.font.bold is True
    assert paragraph.font.size == Pt(20)
    assert shape.text_frame.margin_left == Inches(0)


def test_canvas_bullets_box_uses_shape_to_fit_text():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    shape = _canvas().add_bullets_box(slide, ["One", "Two"], 1, 1, 4, 2)

    assert shape.text_frame.auto_size == MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
    assert "One" in shape.text


def test_canvas_add_slide_image_logs_failure(caplog):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    with caplog.at_level(logging.WARNING):
        inserted = _canvas().add_slide_image(slide, "bad image", 0, 0, 1, 1)

    assert inserted is False
    assert "Failed to insert slide image" in caplog.text


def test_canvas_add_slide_image_inserts_picture():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    one_px_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="

    inserted = _canvas().add_slide_image(slide, one_px_png, 0, 0, 1, 1)

    assert inserted is True
    assert any(shape.shape_type == MSO_SHAPE_TYPE.PICTURE for shape in slide.shapes)
```

- [ ] **Step 3: Instantiate canvas in `PptxEngine.__init__`**

In `backend/app/services/pptx_engine.py`, import:

```python
from app.services.pptx_canvas import PptxCanvas
```

Add this at the end of `__init__`:

```python
self.canvas = PptxCanvas(
    canvas_width=self._canvas_w,
    canvas_height=self._canvas_h,
    logical_width=self._LOGICAL_WIDTH,
    theme=self.theme,
    active_theme=self._active_theme,
    map_color=self._map_color,
)
```

- [ ] **Step 4: Keep compatibility wrappers in `PptxEngine`**

Replace the bodies of these engine helpers with one-line delegations:

```python
def _ix(self, value: float) -> Inches:
    return self.canvas.ix(value)

def _iy(self, value: float) -> Inches:
    return self.canvas.iy(value)

def _add_text(self, slide, left: float, top: float, width: float, height: float, text: str, size: int, color: RGBColor, *, bold: bool = False, align: PP_ALIGN | None = None):
    return self.canvas.add_text(slide, left, top, width, height, text, size, color, bold=bold, align=align)

def _add_card_text(self, slide, x: float, y: float, w: float, h: float, text: str, size: int, color: RGBColor):
    return self.canvas.add_card_text(slide, x, y, w, h, text, size, color)

def _add_bullets_box(self, slide, bullets: list[str], left: float, top: float, width: float, height: float):
    return self.canvas.add_bullets_box(slide, bullets, left, top, width, height)

def _add_card(self, slide, x: float, y: float, w: float, h: float, border_color: RGBColor | None = None):
    return self.canvas.add_card(slide, x, y, w, h, border_color)

def _add_icon_chip(self, slide, x: float, y: float, size: float = 0.62, icon: str | None = None) -> None:
    self.canvas.add_icon_chip(slide, x, y, size, icon)

def _add_accent_bar(self, slide, left: float, top: float, width: float, height: float = 0.05) -> None:
    self.canvas.add_accent_bar(slide, left, top, width, height)

def _add_vertical_divider(self, slide, left: float, top: float, height: float):
    return self.canvas.add_vertical_divider(slide, left, top, height)

def _add_number_circle(self, slide, x: float, y: float, number: int, size: float = 0.72) -> None:
    self.canvas.add_number_circle(slide, x, y, number, size)

def _add_slide_image(self, slide, image_b64, left: float, top: float, width: float, height: float) -> bool:
    return self.canvas.add_slide_image(slide, image_b64, left, top, width, height)

def _add_scrim(self, slide, color: RGBColor = RGBColor(0x0A, 0x16, 0x28), opacity: int = 58) -> None:
    self.canvas.add_scrim(slide, color, opacity)
```

- [ ] **Step 5: Remove imports no longer used by `pptx_engine.py`**

After the wrappers compile, remove unused imports from `pptx_engine.py`, including local image imports that moved to `pptx_canvas.py`:

```python
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.oxml.ns import qn
from app.services.icons import render_icon_png
```

Keep imports still used by engine layout code:

```python
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
```

- [ ] **Step 6: Run canvas and engine tests**

Run from `backend/`:

```bash
uv run pytest tests/test_pptx_canvas.py tests/test_pptx_engine.py -v
```

Expected: all tests pass, including `test_add_slide_image_logs_decode_failure`.

---

### Task 4: Replace Variant And Content Routing With Registries

**Files:**
- Modify: `backend/app/services/pptx_engine.py`
- Modify: `backend/tests/test_pptx_engine.py`

- [ ] **Step 1: Add registry helpers to `PptxEngine`**

Add these methods near `_apply_content_slide`:

```python
def _content_layout_handlers(self):
    return {
        "section_divider": self._apply_section_divider,
        "executive_summary": self._apply_executive_summary,
        "next_steps": self._apply_next_steps,
        "chart": self._apply_chart_slide,
    }

def _framework_variant_handlers(self):
    return {
        "big_statement": self._apply_big_statement,
        "three_points": self._apply_three_points,
        "split_image": self._apply_split_image,
        "big_stat": self._apply_big_stat,
        "before_after": self._apply_before_after,
        "comparison_table": self._apply_comparison_table,
        "process": self._apply_process_variant,
        "quote": self._apply_quote_variant,
        "closing": self._apply_closing,
    }
```

- [ ] **Step 2: Replace `_apply_framework_variant`**

Replace the method body with:

```python
def _apply_framework_variant(self, slide, data: SlideData, variant: str) -> None:
    handler = self._framework_variant_handlers().get(variant, self._apply_standard_content)
    handler(slide, data)
```

- [ ] **Step 3: Replace `_apply_content_slide` while preserving priority order**

Replace the method body with:

```python
def _apply_content_slide(self, slide, data: SlideData):
    layout = data.layout.lower()
    variant = self._variant_for(data)
    layout_handlers = self._content_layout_handlers()
    variant_handlers = self._framework_variant_handlers()

    if layout == "section_divider":
        layout_handlers[layout](slide, data)
        return
    if data.chart_data:
        self._apply_chart_slide(slide, data)
        return
    if variant in variant_handlers:
        variant_handlers[variant](slide, data)
        return
    if getattr(data, "image_b64", None):
        self._apply_split_image(slide, data)
        return
    if getattr(data, "blocks", None):
        self._apply_blocks(slide, data)
        return

    handler = layout_handlers.get(layout, self._apply_standard_content)
    handler(slide, data)
```

- [ ] **Step 4: Add a registry coverage test**

Append:

```python
def test_framework_variant_registry_contains_dark_variants():
    engine = PptxEngine()

    handlers = engine._framework_variant_handlers()

    assert PptxEngine._DARK_VARIANTS.issubset(handlers.keys())
```

- [ ] **Step 5: Run focused tests**

Run from `backend/`:

```bash
uv run pytest tests/test_pptx_engine.py -v
```

Expected: all tests pass.

---

### Task 5: Remove Fragile Dark-State Mutation With A Scoped Theme Override

**Files:**
- Modify: `backend/app/services/pptx_engine.py`
- Modify: `backend/app/services/pptx_canvas.py`
- Modify: `backend/tests/test_pptx_engine.py`

- [ ] **Step 1: Add an engine context manager**

In `pptx_engine.py`, import:

```python
from contextlib import contextmanager
from collections.abc import Iterator
```

Add this method near `_active_theme`:

```python
@contextmanager
def _theme_mode(self, *, dark: bool) -> Iterator[None]:
    previous = self._active_dark
    self._active_dark = dark
    try:
        yield
    finally:
        self._active_dark = previous
```

- [ ] **Step 2: Replace manual mutation in `_apply_split_image`**

Replace:

```python
was_dark = self._active_dark
self._active_dark = True
try:
    self._add_eyebrow(slide, left, top, getattr(data, "kicker", None) or "CURRENT STATE")
    self._add_text(slide, left, top + 0.55, 7.9, 1.7, data.title, 34, self.theme.text, bold=True)
    text_top = top + 2.55
    if data.subtitle:
        self._add_text(slide, left, text_top, 7.2, 0.8, data.subtitle, 19, self.theme.muted)
        text_top += 1.0
    if data.bullets:
        self._add_bullets_box(slide, data.bullets[:4], left, text_top, 7.2, 3.0)
finally:
    self._active_dark = was_dark
```

with:

```python
with self._theme_mode(dark=True):
    self._add_eyebrow(slide, left, top, getattr(data, "kicker", None) or "CURRENT STATE")
    self._add_text(slide, left, top + 0.55, 7.9, 1.7, data.title, 34, self.theme.text, bold=True)
    text_top = top + 2.55
    if data.subtitle:
        self._add_text(slide, left, text_top, 7.2, 0.8, data.subtitle, 19, self.theme.muted)
        text_top += 1.0
    if data.bullets:
        self._add_bullets_box(slide, data.bullets[:4], left, text_top, 7.2, 3.0)
```

- [ ] **Step 3: Strengthen the restoration test for exceptions**

Append:

```python
def test_theme_mode_restores_active_dark_after_exception():
    engine = PptxEngine(theme="minimalist")
    engine._active_dark = False

    with pytest.raises(RuntimeError):
        with engine._theme_mode(dark=True):
            assert engine._active_dark is True
            raise RuntimeError("boom")

    assert engine._active_dark is False
```

- [ ] **Step 4: Run focused tests**

Run from `backend/`:

```bash
uv run pytest tests/test_pptx_engine.py -v
```

Expected: all tests pass.

---

### Task 6: Add Slide And Presentation Type Hints

**Files:**
- Modify: `backend/app/services/pptx_engine.py`
- Modify: `backend/app/services/pptx_canvas.py`

- [ ] **Step 1: Import python-pptx types**

In `pptx_engine.py`, add:

```python
from pptx.presentation import Presentation as PresentationType
from pptx.slide import Slide, SlideLayout
```

- [ ] **Step 2: Type the core engine methods**

Update method signatures:

```python
def _apply_background(self, slide: Slide) -> None:
def _blank_layout(self, prs: PresentationType) -> SlideLayout:
def _find_layout(self, prs: PresentationType, layout_name: str) -> SlideLayout:
def _apply_title_slide(self, slide: Slide, data: SlideData) -> None:
def _apply_content_slide(self, slide: Slide, data: SlideData) -> None:
def _apply_framework_variant(self, slide: Slide, data: SlideData, variant: str) -> None:
def _add_speaker_notes(self, slide: Slide, notes: str) -> None:
def _add_brand_header(self, slide: Slide, slide_width: int) -> None:
```

Update remaining `_apply_*`, `_block_*`, and drawing wrapper signatures opportunistically in the same edit when the return type is obvious.

- [ ] **Step 3: Run ruff and tests**

Run from `backend/`:

```bash
uv run ruff check app/ tests/
uv run pytest tests/test_pptx_canvas.py tests/test_pptx_engine.py -v
```

Expected: ruff passes and tests pass.

---

### Task 7: Final Cleanup And Full Backend Verification

**Files:**
- Modify: `backend/app/services/pptx_engine.py`
- Modify: `backend/app/services/pptx_canvas.py`
- Modify: `backend/tests/test_pptx_engine.py`
- Modify: `backend/tests/test_pptx_canvas.py`

- [ ] **Step 1: Remove obsolete local imports and `print()`**

Verify:

```bash
rg -n "import base64|import io as _io|print\\(" app/services/pptx_engine.py
```

Expected: no output.

- [ ] **Step 2: Remove now-unused imports**

Run:

```bash
uv run ruff check app/ tests/
```

If ruff reports unused imports, remove only the imports it names.

- [ ] **Step 3: Run the backend test order from AGENTS.md**

Run from `backend/`:

```bash
uv run ruff check app/ tests/
uv run pytest
```

Expected: ruff passes and the full backend pytest suite passes.

- [ ] **Step 4: Review resulting file sizes**

Run:

```bash
wc -l app/services/pptx_engine.py app/services/pptx_canvas.py app/services/pptx_layout.py
```

Expected: `pptx_engine.py` is materially smaller, and python-pptx primitive boilerplate lives in `pptx_canvas.py`.

---

## Follow-Up Plan After This Refactor

After the above lands cleanly, split slide layout methods into `backend/app/services/pptx_layouts.py` or a `pptx_layouts/` package. Do not do that in the same change unless the canvas extraction is already merged and stable, because moving both primitives and every layout at once will make regressions harder to isolate.

## Self-Review

- Spec coverage: The plan covers constants, canvas extraction, registry routing, dark-state scoping, logging, import cleanup, type hints, and testing.
- Placeholder scan: No implementation step relies on TBDs or undefined helper names.
- Type consistency: `PptxCanvas` uses `Slide`, `Theme`, `RGBColor`, `PP_ALIGN`, and existing text/icon helpers imported from current modules.

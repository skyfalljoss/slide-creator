from dataclasses import dataclass

from pptx.dml.color import RGBColor

CITI_BLUE = RGBColor(0x05, 0x6D, 0xAE)
CITI_NAVY = RGBColor(0x00, 0x3B, 0x70)
CITI_RED = RGBColor(0xE3, 0x18, 0x37)
CITI_DARK = RGBColor(0x1E, 0x29, 0x3B)
MID_GRAY = RGBColor(0x80, 0x80, 0x80)
LIGHT_GRAY = RGBColor(0xF3, 0xF5, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PANEL_BORDER = RGBColor(0xD8, 0xDE, 0xE8)

TEMPLATE_RED = RGBColor(0xEE, 0x2A, 0x24)
TEMPLATE_NAVY = RGBColor(0x00, 0x3B, 0x70)
SURFACE = RGBColor(0xF7, 0xF8, 0xF9)
CARD_BORDER = RGBColor(0xDC, 0xE0, 0xE5)
TEMPLATE_MUTED = RGBColor(0x5B, 0x67, 0x70)
RED_SOFT = RGBColor(0xFB, 0xE2, 0xE1)


@dataclass(frozen=True)
class Theme:
    accent: RGBColor
    strong: RGBColor
    danger: RGBColor
    text: RGBColor
    muted: RGBColor
    panel_bg: RGBColor
    panel_border: RGBColor
    surface: RGBColor
    border: RGBColor
    accent_soft: RGBColor
    background: RGBColor | None
    accent_weight: float
    use_template: bool


THEMES: dict[str, Theme] = {
    "minimalist": Theme(
        accent=TEMPLATE_RED, strong=TEMPLATE_NAVY, danger=TEMPLATE_RED, text=TEMPLATE_NAVY,
        muted=TEMPLATE_MUTED, panel_bg=SURFACE, panel_border=CARD_BORDER,
        surface=SURFACE, border=CARD_BORDER, accent_soft=RED_SOFT,
        background=WHITE, accent_weight=1.0, use_template=False,
    ),
    "bold": Theme(
        accent=TEMPLATE_RED, strong=TEMPLATE_NAVY, danger=TEMPLATE_RED, text=TEMPLATE_NAVY,
        muted=RGBColor(0x3F, 0x4A, 0x57), panel_bg=RGBColor(0xEE, 0xF1, 0xF4), panel_border=TEMPLATE_NAVY,
        surface=RGBColor(0xEE, 0xF1, 0xF4), border=TEMPLATE_NAVY, accent_soft=RED_SOFT,
        background=WHITE, accent_weight=2.4, use_template=False,
    ),
    "dark": Theme(
        accent=RGBColor(0xF2, 0x6A, 0x5F), strong=RGBColor(0xE8, 0xEE, 0xF5),
        danger=RGBColor(0xF2, 0x6A, 0x7E), text=RGBColor(0xF1, 0xF5, 0xF9),
        muted=RGBColor(0x9F, 0xAD, 0xBD), panel_bg=RGBColor(0x16, 0x24, 0x38),
        panel_border=RGBColor(0x33, 0x41, 0x55),
        surface=RGBColor(0x16, 0x24, 0x38), border=RGBColor(0x33, 0x41, 0x55),
        accent_soft=RGBColor(0x3A, 0x20, 0x22),
        background=RGBColor(0x0F, 0x1B, 0x2D), accent_weight=1.6, use_template=False,
    ),
}


def resolve_theme(name: str | None) -> Theme:
    return THEMES.get(name or "minimalist", THEMES["minimalist"])

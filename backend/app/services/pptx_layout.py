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

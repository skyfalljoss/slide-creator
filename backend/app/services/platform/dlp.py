import re
from math import isfinite

from pydantic import BaseModel

from app.models.schemas import SlideData

PROHIBITED_PATTERNS = [
    ("guarantee returns", re.compile(r"\bguarantee[\s-]+returns\b", re.IGNORECASE)),
    ("guaranteed profit", re.compile(r"\bguaranteed[\s-]+profit\b", re.IGNORECASE)),
    ("risk-free", re.compile(r"\brisk[\s-]+free\b", re.IGNORECASE)),
    ("no risk", re.compile(r"\bno[\s-]+risk\b", re.IGNORECASE)),
    ("certain return", re.compile(r"\bcertain[\s-]+return\b", re.IGNORECASE)),
    ("promised return", re.compile(r"\bpromised[\s-]+return\b", re.IGNORECASE)),
]

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ACCOUNT_RE = re.compile(r"\b\d{10,16}\b")


class DlpService:
    def scan_text(self, text: str) -> list[str]:
        violations = []
        for violation, pattern in PROHIBITED_PATTERNS:
            if pattern.search(text):
                violations.append(violation)
        if EMAIL_RE.search(text):
            violations.append("email address")
        if ACCOUNT_RE.search(text):
            violations.append("account-like number")
        return violations

    def scan_prompt(self, text: str) -> list[str]:
        return self.scan_text(text)

    def scan_slide(self, slide: SlideData) -> list[str]:
        payload = slide.model_dump(exclude={"image_b64"})
        text = "\n".join(self._collect_text(payload))
        return self.scan_text(text)

    def _collect_text(self, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, BaseModel):
            return self._collect_text(value.model_dump())
        if isinstance(value, dict):
            text: list[str] = []
            for key, item in value.items():
                text.append(str(key))
                text.extend(self._collect_text(item))
            return text
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            text = []
            for item in value:
                text.extend(self._collect_text(item))
            return text
        if isinstance(value, int) and not isinstance(value, bool):
            text = str(value)
            return [text] if ACCOUNT_RE.fullmatch(text) else []
        if isinstance(value, float) and isfinite(value) and value.is_integer():
            text = str(int(value))
            return [text] if ACCOUNT_RE.fullmatch(text) else []
        return []

    def scan_slides(self, slides_text: list[str | SlideData]) -> list[dict]:
        flagged = []
        for i, slide_or_text in enumerate(slides_text, start=1):
            violations = self.scan_slide(slide_or_text) if isinstance(slide_or_text, SlideData) else self.scan_text(slide_or_text)
            if violations:
                flagged.append({"slide_index": i, "violations": violations})
        return flagged

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel


AuditAction = Literal["generate", "refine", "export"]


class AuditEvent(BaseModel):
    model_config = {"frozen": True}

    action: AuditAction
    session_id: str
    deck_id: str | None = None
    deck_type: str
    slide_count: int
    slide_index: int | None = None
    user_id: str = "local-user"
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    timestamp: datetime


class AuditService:
    def __init__(self):
        self._events: list[AuditEvent] = []

    def record(
        self,
        *,
        action: AuditAction,
        session_id: str,
        deck_id: str | None = None,
        deck_type: str,
        slide_count: int,
        slide_index: int | None = None,
        user_id: str = "local-user",
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            action=action,
            session_id=session_id,
            deck_id=deck_id,
            deck_type=deck_type,
            slide_count=slide_count,
            slide_index=slide_index,
            user_id=user_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            timestamp=datetime.now(timezone.utc),
        )
        self._events.append(event)
        return event

    def get_events(self) -> list[AuditEvent]:
        return list(self._events)

    def clear_events(self) -> None:
        self._events.clear()

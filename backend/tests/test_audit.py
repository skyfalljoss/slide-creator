import pytest
from starlette.requests import Request

from app.services.audit import AuditService
from app.services.auth import get_user_id


def make_request(user_id: str | None = None) -> Request:
    headers = [] if user_id is None else [(b"x-user-id", user_id.encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_audit_records_metadata_only():
    audit = AuditService()

    event = audit.record(
        action="generate",
        session_id="session-123",
        deck_type="sales_9",
        slide_count=9,
    )

    assert event.action == "generate"
    assert event.session_id == "session-123"
    assert event.deck_type == "sales_9"
    assert event.slide_count == 9
    assert event.slide_index is None
    assert not hasattr(event, "prompt")
    assert not hasattr(event, "slides")


def test_audit_records_user_model_and_token_metadata():
    audit = AuditService()

    event = audit.record(
        action="generate",
        session_id="session-123",
        deck_type="sales_9",
        slide_count=9,
        user_id="local-user",
        model="gemini-1.5-pro",
        input_tokens=120,
        output_tokens=500,
    )

    assert event.user_id == "local-user"
    assert event.model == "gemini-1.5-pro"
    assert event.input_tokens == 120
    assert event.output_tokens == 500


def test_audit_events_returned_from_history_cannot_mutate_stored_history():
    audit = AuditService()
    audit.record(action="generate", session_id="session-123", deck_type="sales_9", slide_count=9)

    event = audit.get_events()[0]

    with pytest.raises(Exception):
        event.session_id = "tampered"

    assert audit.get_events()[0].session_id == "session-123"


def test_get_user_id_returns_safe_header_value():
    assert get_user_id(make_request("abc-123")) == "abc-123"


@pytest.mark.parametrize("user_id", ["jane@example.com secret", "a" * 65])
def test_get_user_id_falls_back_for_invalid_header_values(user_id: str):
    assert get_user_id(make_request(user_id)) == "local-user"


def test_audit_can_clear_events_for_tests():
    audit = AuditService()
    audit.record(action="export", session_id="session-123", deck_type="internal_6", slide_count=6)

    assert len(audit.get_events()) == 1

    audit.clear_events()

    assert audit.get_events() == []

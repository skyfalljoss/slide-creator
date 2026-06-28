from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app import dependencies
from app.errors import StorageError
from app.main import app
from app.models.schemas import SlideData
from app.services.platform.deck_repository import DeckRecord, DeckVersionRecord


def _deck_record(deck_id: str = "deck-123") -> DeckRecord:
    now = datetime.now(timezone.utc)
    version = DeckVersionRecord(
        id="version-123",
        deck_id=deck_id,
        version_number=1,
        storage_key=f"decks/{deck_id}/versions/version-123.pptx",
        sha256="a" * 64,
        size_bytes=1234,
        source="generated",
        created_by="generation",
        created_at=now,
    )
    return DeckRecord(
        id=deck_id,
        owner_id="banker-123",
        name="Quarterly Review",
        deck_type="sales_9",
        theme="dark",
        aspect_ratio="4:3",
        generation_payload={"slides": []},
        current_version_id=version.id,
        created_at=now,
        updated_at=now,
        current_version=version,
    )


class FakeGenerator:
    def __init__(self, title: str = " Quarterly Review ") -> None:
        self.title = title

    async def generate(self, _req, chart_data=None, upload_summary=None):
        return [
            SlideData(
                index=1,
                title=self.title,
                bullets=["Safe content"],
                notes="Safe notes",
                layout="title",
            )
        ]


class RecordingDeckVersionService:
    def __init__(self, events: list[str], error: Exception | None = None) -> None:
        self.events = events
        self.error = error
        self.calls: list[dict] = []

    async def create_generated_deck(self, **kwargs):
        self.events.append("persist:start")
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        self.events.append("persist:complete")
        return _deck_record()


class RecordingSessionStore:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.created = 0

    def create(self, _slides, _deck_type, _theme, _aspect_ratio):
        self.events.append("session")
        self.created += 1
        return "session-123"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value
    app.dependency_overrides.clear()


def _override_generation(decks, sessions, generator=None) -> None:
    app.dependency_overrides[dependencies.get_deck_version_service] = lambda: decks
    app.dependency_overrides[dependencies.get_session_store] = lambda: sessions
    app.dependency_overrides[dependencies.get_generator_service] = lambda: generator or FakeGenerator()


@pytest.mark.asyncio
async def test_generate_persists_before_creating_compatibility_session(client: AsyncClient):
    events: list[str] = []
    decks = RecordingDeckVersionService(events)
    sessions = RecordingSessionStore(events)
    _override_generation(decks, sessions)
    audit = dependencies.get_audit_service()
    audit.clear_events()

    response = await client.post(
        "/api/v1/generate",
        headers={"x-user-id": "banker-123"},
        json={
            "prompt": "Create a safe deck",
            "deck_type": "sales_9",
            "theme": "dark",
            "aspect_ratio": "4:3",
        },
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "session-123"
    assert response.json()["deck_id"] == "deck-123"
    assert response.json()["editor_path"] == "/editor/deck-123"
    assert events == ["persist:start", "persist:complete", "session"]
    call = decks.calls[0]
    assert call["owner_id"] == "banker-123"
    assert call["name"] == "Quarterly Review"
    assert call["deck_type"] == "sales_9"
    assert call["theme"] == "dark"
    assert call["aspect_ratio"] == "4:3"
    assert call["slides"][0].title == " Quarterly Review "
    assert [slide.model_dump(mode="json") for slide in call["slides"]] == response.json()[
        "slides"
    ]
    event = audit.get_events()[-1]
    assert event.session_id == "session-123"
    assert event.deck_id == "deck-123"
    audit.clear_events()


@pytest.mark.asyncio
async def test_generate_does_not_create_session_or_audit_when_persistence_fails(client: AsyncClient):
    events: list[str] = []
    decks = RecordingDeckVersionService(events, StorageError("write failed"))
    sessions = RecordingSessionStore(events)
    _override_generation(decks, sessions)
    audit = dependencies.get_audit_service()
    audit.clear_events()

    response = await client.post(
        "/api/v1/generate",
        json={"prompt": "Create a safe deck", "deck_type": "sales_9"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "STORAGE_ERROR", "message": "write failed"}
    }
    assert events == ["persist:start"]
    assert sessions.created == 0
    assert audit.get_events() == []


@pytest.mark.asyncio
async def test_generate_dlp_failure_skips_persistence_and_session(client: AsyncClient):
    events: list[str] = []
    decks = RecordingDeckVersionService(events)
    sessions = RecordingSessionStore(events)
    _override_generation(decks, sessions, FakeGenerator("Guarantee returns"))

    response = await client.post(
        "/api/v1/generate",
        json={"prompt": "Create a safe deck", "deck_type": "sales_9"},
    )

    assert response.status_code == 400
    assert events == []
    assert decks.calls == []
    assert sessions.created == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("title", "expected"),
    [("   ", "Untitled Deck"), ("x" * 700, "x" * 500)],
)
async def test_generate_uses_bounded_nonempty_persisted_name(
    client: AsyncClient,
    title: str,
    expected: str,
):
    events: list[str] = []
    decks = RecordingDeckVersionService(events)
    sessions = RecordingSessionStore(events)
    _override_generation(decks, sessions, FakeGenerator(title))

    response = await client.post(
        "/api/v1/generate",
        json={"prompt": "Create a safe deck"},
    )

    assert response.status_code == 200
    assert decks.calls[0]["name"] == expected
    assert decks.calls[0]["deck_type"] == "unknown"

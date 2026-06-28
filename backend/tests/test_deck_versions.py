import hashlib
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock
import pytest

from app.models.schemas import SlideData
from app.services.platform.deck_repository import DeckRecord, DeckVersionRecord
from app.services.platform.deck_versions import DeckVersionService, VersionStorageConflictError
from app.services.presentation.pptx_validation import InvalidPptxError, validate_pptx


NOW = datetime.now(timezone.utc)


def slide(title: str = "A title") -> SlideData:
    return SlideData(
        index=1,
        title=title,
        bullets=["A point"],
        notes="Notes",
        layout="title",
    )


def pptx_bytes(title: str = "A title") -> bytes:
    from pptx import Presentation

    presentation = Presentation()
    page = presentation.slides.add_slide(presentation.slide_layouts[6])
    page.shapes.title if page.shapes.title else None
    page.notes_slide.notes_text_frame.text = title
    output = BytesIO()
    presentation.save(output)
    return output.getvalue()


def version_record(
    *,
    deck_id: str = "deck-1",
    version_id: str = "version-1",
    version_number: int = 1,
    storage_key: str | None = None,
    sha256: str = "checksum",
    size_bytes: int = 123,
    source: str = "generated",
) -> DeckVersionRecord:
    return DeckVersionRecord(
        id=version_id,
        deck_id=deck_id,
        version_number=version_number,
        storage_key=storage_key or f"decks/{deck_id}/versions/{version_id}.pptx",
        sha256=sha256,
        size_bytes=size_bytes,
        source=source,
        created_by="owner-1",
        created_at=NOW,
    )


def deck_record(version: DeckVersionRecord) -> DeckRecord:
    return DeckRecord(
        id=version.deck_id,
        owner_id="owner-1",
        name="Deck",
        deck_type="pitch",
        theme="citi",
        aspect_ratio="16:9",
        generation_payload={"slides": [slide().model_dump(mode="json")]},
        current_version_id=version.id,
        created_at=NOW,
        updated_at=NOW,
        current_version=version,
    )


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.events: list[str] = []
        self.delete_error: Exception | None = None
        self.delete_errors: set[str] = set()

    async def put(self, key: str, content: bytes) -> None:
        self.events.append("upload")
        if key in self.objects:
            raise FileExistsError(key)
        self.objects[key] = content

    async def read(self, key: str) -> bytes:
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.events.append("delete")
        if self.delete_error or key in self.delete_errors:
            raise self.delete_error or OSError("delete failed")
        self.objects.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self.objects

    async def list_keys(self, prefix: str) -> list[str]:
        return sorted(key for key in self.objects if key.startswith(prefix))


class InitialRepository:
    def __init__(self, storage: FakeStorage) -> None:
        self.storage = storage
        self.kwargs: dict | None = None
        self.error: Exception | None = None

    async def create_with_initial_version(self, **kwargs) -> DeckRecord:
        assert self.storage.events == ["upload"]
        self.kwargs = kwargs
        if self.error:
            raise self.error
        version = version_record(
            deck_id=kwargs["deck_id"],
            version_id=kwargs["version_id"],
            storage_key=kwargs["storage_key"],
            sha256=kwargs["sha256"],
            size_bytes=kwargs["size_bytes"],
        )
        return deck_record(version)


class VersionRepository:
    def __init__(self, current: DeckRecord | None = None) -> None:
        self.current = current
        self.versions: dict[str, DeckVersionRecord] = {}
        if current is not None and current.current_version is not None:
            self.versions[current.current_version.id] = current.current_version
        self.version_results: list[DeckVersionRecord | None] = []
        self.append_calls: list[dict] = []
        self.deleted_row_batches: list[list[str]] = []
        self.delete_rows_error: Exception | None = None

    async def get(self, deck_id: str, owner_id: str) -> DeckRecord | None:
        if self.current is None or self.current.id != deck_id or self.current.owner_id != owner_id:
            return None
        return self.current

    async def version(
        self, deck_id: str, version_id: str, owner_id: str
    ) -> DeckVersionRecord | None:
        if self.version_results:
            return self.version_results.pop(0)
        result = self.versions.get(version_id)
        if result is None or result.deck_id != deck_id or owner_id != "owner-1":
            return None
        return result

    async def append_version(self, **kwargs) -> DeckVersionRecord:
        self.append_calls.append(kwargs)
        result = version_record(
            deck_id=kwargs["deck_id"],
            version_id=kwargs["version_id"],
            version_number=(self.current.current_version.version_number + 1),
            storage_key=kwargs["storage_key"],
            sha256=kwargs["sha256"],
            source=kwargs["source"],
        )
        self.versions[result.id] = result
        assert self.current is not None
        self.current = DeckRecord(
            **{
                **self.current.__dict__,
                "generation_payload": kwargs.get("generation_payload")
                or self.current.generation_payload,
                "current_version_id": result.id,
                "current_version": result,
            }
        )
        return result

    async def stale_versions(self, deck_id: str, keep: int) -> list[DeckVersionRecord]:
        ordered = sorted(
            (version for version in self.versions.values() if version.deck_id == deck_id),
            key=lambda version: version.version_number,
            reverse=True,
        )
        current_id = self.current.current_version_id if self.current is not None else None
        return [version for version in ordered[keep:] if version.id != current_id]

    async def delete_version_rows(self, version_ids: list[str]) -> None:
        self.deleted_row_batches.append(version_ids)
        if self.delete_rows_error:
            raise self.delete_rows_error
        for version_id in version_ids:
            self.versions.pop(version_id, None)


@pytest.mark.asyncio
async def test_create_generated_deck_renders_uploads_then_creates_metadata():
    storage = FakeStorage()
    repository = InitialRepository(storage)
    service = DeckVersionService(
        repository=repository,
        storage=storage,
        sample_template_path=None,
        max_file_bytes=50_000_000,
        retention=5,
    )

    result = await service.create_generated_deck(
        owner_id="owner-1",
        name="Deck",
        deck_type="pitch",
        theme="minimalist",
        aspect_ratio="16:9",
        slides=[slide()],
    )

    assert result.current_version is not None
    assert result.current_version.version_number == 1
    assert repository.kwargs is not None
    assert repository.kwargs["generation_payload"] == {
        "slides": [slide().model_dump(mode="json")]
    }
    key = repository.kwargs["storage_key"]
    assert key == f"decks/{result.id}/versions/{result.current_version.id}.pptx"
    content = await storage.read(key)
    validate_pptx(content, max_bytes=50_000_000)
    assert repository.kwargs["size_bytes"] == len(content)
    assert result.current_version.size_bytes == len(content)
    assert repository.kwargs["sha256"] == hashlib.sha256(content).hexdigest()
    assert result.current_version.sha256 == repository.kwargs["sha256"]


@pytest.mark.asyncio
async def test_create_generated_deck_deletes_upload_when_metadata_fails():
    storage = FakeStorage()
    repository = InitialRepository(storage)
    repository.error = RuntimeError("metadata failed")
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)

    with pytest.raises(RuntimeError, match="metadata failed"):
        await service.create_generated_deck(
            owner_id="owner-1",
            name="Deck",
            deck_type="pitch",
            theme="minimalist",
            aspect_ratio="16:9",
            slides=[slide()],
        )

    assert storage.objects == {}
    assert storage.events == ["upload", "delete"]


@pytest.mark.asyncio
async def test_create_generated_deck_preserves_metadata_error_when_cleanup_fails():
    storage = FakeStorage()
    storage.delete_error = OSError("cleanup failed")
    repository = InitialRepository(storage)
    repository.error = RuntimeError("metadata failed")
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)

    with pytest.raises(RuntimeError, match="metadata failed"):
        await service.create_generated_deck(
            owner_id="owner-1",
            name="Deck",
            deck_type="pitch",
            theme="minimalist",
            aspect_ratio="16:9",
            slides=[slide()],
        )


@pytest.mark.asyncio
async def test_render_runs_off_event_loop(monkeypatch):
    content = pptx_bytes()
    render = AsyncMock(return_value=content)

    async def fake_to_thread(function, *args):
        await render()
        return function(*args)

    monkeypatch.setattr("app.services.platform.deck_versions.asyncio.to_thread", fake_to_thread)
    storage = FakeStorage()
    repository = InitialRepository(storage)
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)

    await service.create_generated_deck(
        owner_id="owner-1",
        name="Deck",
        deck_type="pitch",
        theme="minimalist",
        aspect_ratio="16:9",
        slides=[slide()],
    )

    render.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_edited_version_rejects_invalid_bytes_before_upload():
    current = version_record()
    repository = VersionRepository(deck_record(current))
    storage = FakeStorage()
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)

    with pytest.raises(InvalidPptxError):
        await service.save_edited_version(
            deck_id="deck-1",
            owner_id="owner-1",
            content=b"not a pptx",
            base_version_id=current.id,
            callback_key="callback-1",
            created_by="editor@example.com",
        )

    assert storage.events == []
    assert repository.append_calls == []


@pytest.mark.asyncio
async def test_save_edited_version_appends_onlyoffice_version_and_is_idempotent():
    current = version_record()
    repository = VersionRepository(deck_record(current))
    storage = FakeStorage()
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)
    content = pptx_bytes("edited")

    first = await service.save_edited_version(
        deck_id="deck-1",
        owner_id="owner-1",
        content=content,
        base_version_id=current.id,
        callback_key="callback-1",
        created_by="editor@example.com",
    )
    second = await service.save_edited_version(
        deck_id="deck-1",
        owner_id="owner-1",
        content=content,
        base_version_id=current.id,
        callback_key="callback-1",
        created_by="editor@example.com",
    )

    assert second == first
    assert len(storage.objects) == 1
    assert len(repository.append_calls) == 1
    call = repository.append_calls[0]
    assert call["source"] == "onlyoffice_save"
    assert call["base_version_id"] == current.id
    assert call["created_by"] == "editor@example.com"
    assert first.storage_key == f"decks/deck-1/versions/{first.id}.pptx"


@pytest.mark.asyncio
async def test_save_edited_version_same_callback_different_content_has_distinct_id():
    current = version_record()
    repository = VersionRepository(deck_record(current))
    storage = FakeStorage()
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)

    first = await service.save_edited_version(
        deck_id="deck-1",
        owner_id="owner-1",
        content=pptx_bytes("first"),
        base_version_id=current.id,
        callback_key="callback-1",
        created_by="editor",
    )
    second = await service.save_edited_version(
        deck_id="deck-1",
        owner_id="owner-1",
        content=pptx_bytes("second"),
        base_version_id=current.id,
        callback_key="callback-1",
        created_by="editor",
    )

    assert first.id != second.id
    assert len(repository.append_calls) == 2


@pytest.mark.asyncio
async def test_save_edited_version_file_exists_race_returns_committed_match():
    current = version_record()
    repository = VersionRepository(deck_record(current))
    storage = FakeStorage()
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)
    content = pptx_bytes("race")
    checksum = hashlib.sha256(content).hexdigest()

    # Determine the stable ID without exposing the namespace as public API.
    initial = await service.save_edited_version(
        deck_id="deck-1",
        owner_id="owner-1",
        content=content,
        base_version_id=current.id,
        callback_key="callback-1",
        created_by="editor",
    )
    repository.versions.clear()
    repository.append_calls.clear()
    repository.version_results = [None, None, initial]
    storage.events.clear()

    result = await service.save_edited_version(
        deck_id="deck-1",
        owner_id="owner-1",
        content=content,
        base_version_id=current.id,
        callback_key="callback-1",
        created_by="editor",
    )

    assert result == initial
    assert result.sha256 == checksum
    assert repository.append_calls == []


@pytest.mark.asyncio
async def test_save_edited_version_file_exists_without_metadata_raises():
    current = version_record()
    repository = VersionRepository(deck_record(current))
    storage = FakeStorage()
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)
    content = pptx_bytes("orphan")
    first = await service.save_edited_version(
        deck_id="deck-1",
        owner_id="owner-1",
        content=content,
        base_version_id=current.id,
        callback_key="callback-1",
        created_by="editor",
    )
    repository.versions.pop(first.id)
    repository.append_calls.clear()

    with pytest.raises(VersionStorageConflictError, match="metadata"):
        await service.save_edited_version(
            deck_id="deck-1",
            owner_id="owner-1",
            content=content,
            base_version_id=current.id,
            callback_key="callback-1",
            created_by="editor",
        )

    assert repository.append_calls == []


@pytest.mark.asyncio
async def test_restore_version_copies_owned_source_to_new_current_version():
    current = version_record(version_id="current", version_number=2)
    selected = version_record(version_id="selected", version_number=1)
    repository = VersionRepository(deck_record(current))
    repository.versions[selected.id] = selected
    storage = FakeStorage()
    source_content = pptx_bytes("restore")
    storage.objects[selected.storage_key] = source_content
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)

    restored = await service.restore_version(
        deck_id="deck-1",
        version_id="selected",
        owner_id="owner-1",
        created_by="restorer",
    )

    assert restored.id != selected.id
    assert storage.objects[restored.storage_key] == source_content
    call = repository.append_calls[0]
    assert call["source"] == "restore"
    assert call["base_version_id"] == current.id
    assert call["created_by"] == "restorer"


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_id,version_id", [("other-owner", "selected"), ("owner-1", "missing")])
async def test_restore_version_rejects_missing_or_cross_owner(owner_id: str, version_id: str):
    current = version_record(version_id="current")
    selected = version_record(version_id="selected")
    repository = VersionRepository(deck_record(current))
    repository.versions[selected.id] = selected
    storage = FakeStorage()
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)

    with pytest.raises(LookupError, match="not found"):
        await service.restore_version(
            deck_id="deck-1",
            version_id=version_id,
            owner_id=owner_id,
            created_by="restorer",
        )

    assert storage.events == []


@pytest.mark.asyncio
async def test_save_slides_as_version_renders_and_updates_generation_provenance():
    current = version_record(version_id="current")
    repository = VersionRepository(deck_record(current))
    storage = FakeStorage()
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)
    slides = [slide("New generated slide")]

    result = await service.save_slides_as_version(
        deck_id="deck-1",
        owner_id="owner-1",
        slides=slides,
        theme="minimalist",
        aspect_ratio="16:9",
        created_by="generator",
    )

    validate_pptx(storage.objects[result.storage_key], max_bytes=50_000_000)
    call = repository.append_calls[0]
    assert call["source"] == "generated"
    assert call["base_version_id"] == current.id
    assert call["generation_payload"] == {
        "slides": [item.model_dump(mode="json") for item in slides]
    }


async def save_editor_revision(
    service: DeckVersionService, number: int
) -> DeckVersionRecord:
    return await service.save_edited_version(
        deck_id="deck-1",
        owner_id="owner-1",
        content=pptx_bytes(f"revision-{number}"),
        base_version_id=f"base-{number}",
        callback_key=f"callback-{number}",
        created_by="editor",
    )


@pytest.mark.asyncio
async def test_retention_keeps_newest_five_after_sixth_version():
    initial = version_record(version_id="initial")
    repository = VersionRepository(deck_record(initial))
    storage = FakeStorage()
    storage.objects[initial.storage_key] = pptx_bytes("initial")
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)

    for number in range(1, 5):
        await save_editor_revision(service, number)

    assert len(repository.versions) == 5
    assert initial.id in repository.versions

    await save_editor_revision(service, 5)

    assert len(repository.versions) == 5
    assert len(storage.objects) == 5
    assert "initial" not in repository.versions
    assert initial.storage_key not in storage.objects
    assert repository.current is not None
    assert repository.current.current_version_id in repository.versions


@pytest.mark.asyncio
async def test_retention_leaves_row_when_object_delete_fails():
    initial = version_record(version_id="initial")
    repository = VersionRepository(deck_record(initial))
    storage = FakeStorage()
    storage.objects[initial.storage_key] = pptx_bytes("initial")
    storage.delete_errors.add(initial.storage_key)
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)

    for number in range(1, 6):
        await save_editor_revision(service, number)

    assert initial.id in repository.versions
    assert initial.storage_key in storage.objects
    assert all(initial.id not in batch for batch in repository.deleted_row_batches)


@pytest.mark.asyncio
async def test_retention_row_cleanup_failure_does_not_fail_committed_save():
    initial = version_record(version_id="initial")
    repository = VersionRepository(deck_record(initial))
    repository.delete_rows_error = RuntimeError("row cleanup failed")
    storage = FakeStorage()
    storage.objects[initial.storage_key] = pptx_bytes("initial")
    service = DeckVersionService(repository, storage, None, 50_000_000, 5)

    for number in range(1, 6):
        result = await save_editor_revision(service, number)

    assert repository.current is not None
    assert repository.current.current_version_id == result.id
    assert initial.id in repository.versions
    assert initial.storage_key not in storage.objects

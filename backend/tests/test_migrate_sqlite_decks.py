import json
import sqlite3
import base64
import random
import asyncio
from argparse import Namespace
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO

from pptx import Presentation
from PIL import Image
import pytest

from app.services.platform.database import Database
from app.services.platform.deck_files import LocalDeckFileStorage
from app.services.platform.deck_repository import DeckRepository
from app.services.platform.deck_repository import DeckWriteRolledBackError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import update
from app.services.platform.deck_models import DeckRow
from scripts.migrate_sqlite_decks import migrate_sqlite_decks
from scripts.migrate_sqlite_decks import MigrationLimits
from scripts.migrate_sqlite_decks import _validate_decoded_budget
import scripts.migrate_sqlite_decks as migration_script


class _GuardMixin:
    @asynccontextmanager
    async def storage_key_guard(self, storage_key):
        yield

    async def storage_key_referenced(self, storage_key, *, session=None):
        return False


async def test_migration_cli_uses_configured_lock_dir_for_cross_process_coordination(
    tmp_path, monkeypatch
):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"
    lock_dir = tmp_path / "custom-locks"
    app_database = Database(database_url)
    app_repository = DeckRepository(app_database, lock_dir=lock_dir)

    class Storage:
        async def close(self):
            return None

    async def coordinated_migration(
        _sqlite_path, _owner_id, script_repository, _storage, **_kwargs
    ):
        entered = asyncio.Event()

        async def waiter():
            async with script_repository.storage_key_guard("decks/shared.pptx"):
                entered.set()

        async with app_repository.storage_key_guard("decks/shared.pptx"):
            task = asyncio.create_task(waiter())
            await asyncio.sleep(0.05)
            assert entered.is_set() is False
        await asyncio.wait_for(task, 1)
        assert entered.is_set()
        return migration_script.MigrationResult(0, 0, 0, ())

    monkeypatch.setattr(migration_script.settings, "database_url", database_url)
    monkeypatch.setattr(migration_script.settings, "deck_lock_dir", str(lock_dir))
    monkeypatch.setattr(migration_script, "_storage", lambda: Storage())
    monkeypatch.setattr(migration_script, "migrate_sqlite_decks", coordinated_migration)
    args = Namespace(
        sqlite_path=tmp_path / "legacy.db",
        owner_id="owner",
        max_sqlite_bytes=1,
        max_row_json_bytes=1,
        max_json_depth=1,
        max_slides=1,
        max_total_text_chars=1,
        max_text_chars=1,
        max_list_items=1,
        max_image_item_bytes=1,
        max_image_bytes=1,
        fetch_batch_size=1,
    )
    try:
        assert await migration_script._main(args) == 0
    finally:
        await app_database.dispose()


def _legacy_database(path, rows):
    connection = sqlite3.connect(path)
    connection.execute(
        """CREATE TABLE decks (
            id TEXT PRIMARY KEY, name TEXT, deck_type TEXT, theme TEXT,
            aspect_ratio TEXT, slides TEXT, generation_payload TEXT,
            created_at TEXT, updated_at TEXT
        )"""
    )
    connection.executemany(
        "INSERT INTO decks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    connection.commit()
    connection.close()


async def test_migration_preserves_legacy_metadata_and_renders_version_one(tmp_path):
    source = tmp_path / "legacy.db"
    created = "2024-02-03T04:05:06+00:00"
    updated = "2024-03-04T05:06:07+00:00"
    slides = [
        {"index": 1, "title": "Legacy title", "bullets": [], "notes": "", "layout": "title"}
    ]
    payload = {"slides": slides, "prompt": "preserve this", "file_id": "source-1"}
    _legacy_database(
        source,
        [("legacy-1", "Legacy Deck", "sales_9", "dark", "4:3", json.dumps(slides), json.dumps(payload), created, updated)],
    )
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'target.db'}")
    await database.create_schema()
    repository = DeckRepository(database)
    storage = LocalDeckFileStorage(tmp_path / "files")
    try:
        result = await migrate_sqlite_decks(
            sqlite_path=source,
            owner_id="migration-owner",
            repository=repository,
            storage=storage,
            template_path=None,
        )
        deck = await repository.get("legacy-1", "migration-owner")
        content = await storage.read(deck.current_version.storage_key)
    finally:
        await database.dispose()

    assert result.migrated == 1 and result.skipped == result.failed == 0
    assert deck.id == "legacy-1"
    assert (deck.name, deck.deck_type, deck.theme, deck.aspect_ratio) == (
        "Legacy Deck", "sales_9", "dark", "4:3"
    )
    assert deck.generation_payload == payload
    assert deck.created_at == datetime.fromisoformat(created)
    assert deck.updated_at == datetime.fromisoformat(updated)
    assert deck.current_version.version_number == 1
    assert deck.current_version.created_at == datetime.fromisoformat(created)
    assert len(Presentation(BytesIO(content)).slides) == 1


async def test_migration_is_idempotent_and_isolates_bad_rows(tmp_path):
    source = tmp_path / "legacy.db"
    valid = [{"index": 1, "title": "Good", "bullets": [], "notes": "", "layout": "title"}]
    now = datetime.now(timezone.utc).isoformat()
    _legacy_database(
        source,
        [
            ("good", "Good", "sales", "minimalist", "16:9", json.dumps(valid), None, now, now),
            ("bad", "Bad", "sales", "minimalist", "16:9", "not-json", None, now, now),
        ],
    )
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'target.db'}")
    await database.create_schema()
    repository = DeckRepository(database)
    storage = LocalDeckFileStorage(tmp_path / "files")
    try:
        first = await migrate_sqlite_decks(source, "owner", repository, storage, template_path=None)
        second = await migrate_sqlite_decks(source, "owner", repository, storage, template_path=None)
        versions = await repository.list_versions("good", "owner")
    finally:
        await database.dispose()

    assert (first.migrated, first.failed) == (1, 1)
    assert (second.migrated, second.skipped, second.failed) == (0, 1, 1)
    assert len(versions) == 1


async def test_migration_compensates_definite_rollback_but_preserves_uncertain_upload(tmp_path):
    source = tmp_path / "legacy.db"
    slides = [{"content": {"index": 1, "title": "Nested", "bullets": [], "notes": "", "layout": "title"}}]
    now = datetime.now(timezone.utc).isoformat()
    _legacy_database(
        source,
        [("deck-1", "Deck", "sales", "minimalist", "16:9", json.dumps(slides), None, now, now)],
    )

    class Repository(_GuardMixin):
        def __init__(self, error):
            self.error = error

        async def get_global(self, deck_id, *, session=None):
            return None

        async def import_with_initial_version(self, **kwargs):
            raise self.error

    class Storage:
        def __init__(self):
            self.deleted = []

        async def put(self, key, content):
            return None

        async def delete(self, key):
            self.deleted.append(key)

    rolled_back_storage = Storage()
    uncertain_storage = Storage()
    rolled_back = await migrate_sqlite_decks(
        source,
        "owner",
        Repository(DeckWriteRolledBackError("rolled back", RuntimeError("db"))),
        rolled_back_storage,
        template_path=None,
    )
    uncertain = await migrate_sqlite_decks(
        source,
        "owner",
        Repository(RuntimeError("commit outcome unknown")),
        uncertain_storage,
        template_path=None,
    )

    assert rolled_back.failed == uncertain.failed == 1
    assert len(rolled_back_storage.deleted) == 1
    assert uncertain_storage.deleted == []


async def test_guard_exit_rollback_compensates_and_does_not_stop_following_row(tmp_path):
    source = tmp_path / "legacy.db"
    slides = [{"index": 1, "title": "One", "bullets": [], "notes": "", "layout": "title"}]
    now = datetime.now(timezone.utc).isoformat()
    _legacy_database(
        source,
        [
            ("a-rollback", "Rollback", "sales", "minimalist", "16:9", json.dumps(slides), None, now, now),
            ("z-good", "Good", "sales", "minimalist", "16:9", json.dumps(slides), None, now, now),
        ],
    )

    class Repository:
        def __init__(self):
            self.guard_entries = {}

        @asynccontextmanager
        async def storage_key_guard(self, storage_key):
            self.guard_entries[storage_key] = self.guard_entries.get(storage_key, 0) + 1
            session = object()
            try:
                yield session
            except SQLAlchemyError as cause:
                raise DeckWriteRolledBackError("body rolled back", cause) from cause
            if "a-rollback" in storage_key and self.guard_entries[storage_key] == 1:
                raise DeckWriteRolledBackError(
                    "commit rolled back", SQLAlchemyError("commit failed")
                )

        async def get_global(self, deck_id, *, session=None):
            return None

        async def import_with_initial_version(self, **kwargs):
            return None

        async def storage_key_referenced(self, storage_key, *, session=None):
            assert session is not None
            return False

    class Storage:
        def __init__(self):
            self.objects = set()
            self.deleted = []

        async def put(self, key, content):
            self.objects.add(key)

        async def read(self, key):
            raise KeyError(key)

        async def delete(self, key):
            self.deleted.append(key)
            self.objects.discard(key)

    repository = Repository()
    storage = Storage()
    result = await migrate_sqlite_decks(
        source, "owner", repository, storage, template_path=None
    )

    rollback_key = next(key for key in repository.guard_entries if "a-rollback" in key)
    assert repository.guard_entries[rollback_key] == 2
    assert (result.migrated, result.failed) == (1, 1)
    assert storage.deleted == [rollback_key]
    assert all("z-good" in key for key in storage.objects)


async def test_existing_id_requires_same_owner_and_exact_authoritative_identity(tmp_path):
    source = tmp_path / "legacy.db"
    slides = [{"index": 1, "title": "One", "bullets": [], "notes": "", "layout": "title"}]
    now = datetime.now(timezone.utc).isoformat()
    _legacy_database(
        source,
        [("legacy", "Original", "sales", "minimalist", "16:9", json.dumps(slides), None, now, now)],
    )
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'target.db'}")
    await database.create_schema()
    repository = DeckRepository(database)
    storage = LocalDeckFileStorage(tmp_path / "files")
    try:
        first = await migrate_sqlite_decks(source, "owner-a", repository, storage, template_path=None)
        matching = await migrate_sqlite_decks(source, "owner-a", repository, storage, template_path=None)
        collision = await migrate_sqlite_decks(source, "owner-b", repository, storage, template_path=None)
        async with database.session() as session, session.begin():
            await session.execute(
                update(DeckRow).where(DeckRow.id == "legacy").values(name="Changed")
            )
        mismatch = await migrate_sqlite_decks(source, "owner-a", repository, storage, template_path=None)
        async with database.session() as session, session.begin():
            await session.execute(
                update(DeckRow)
                .where(DeckRow.id == "legacy")
                .values(name="Original", current_version_id=None)
            )
        incomplete = await migrate_sqlite_decks(
            source, "owner-a", repository, storage, template_path=None
        )
    finally:
        await database.dispose()

    assert first.migrated == 1
    assert (matching.skipped, matching.failed) == (1, 0)
    assert (collision.skipped, collision.failed) == (0, 1)
    assert (mismatch.skipped, mismatch.failed) == (0, 1)
    assert (incomplete.skipped, incomplete.failed) == (0, 1)


async def test_concurrent_matching_winner_is_reconciled_without_deleting_object(tmp_path):
    source = tmp_path / "legacy.db"
    slides = [{"index": 1, "title": "One", "bullets": [], "notes": "", "layout": "title"}]
    now = datetime.now(timezone.utc).isoformat()
    _legacy_database(
        source,
        [("legacy", "Original", "sales", "minimalist", "16:9", json.dumps(slides), None, now, now)],
    )
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'target.db'}")
    await database.create_schema()
    real = DeckRepository(database)
    storage = LocalDeckFileStorage(tmp_path / "files")

    class ConcurrentWinner(_GuardMixin):
        async def get_global(self, deck_id, *, session=None):
            return await real.get_global(deck_id)

        async def import_with_initial_version(self, **kwargs):
            await real.import_with_initial_version(**kwargs)
            raise DeckWriteRolledBackError("lost race", RuntimeError("unique conflict"))

    try:
        result = await migrate_sqlite_decks(
            source, "owner", ConcurrentWinner(), storage, template_path=None
        )
        deck = await real.get("legacy", "owner")
        exists = await storage.exists(deck.current_version.storage_key)
    finally:
        await database.dispose()

    assert (result.migrated, result.skipped, result.failed) == (0, 1, 0)
    assert exists is True


async def test_compensation_delete_failure_does_not_stop_following_rows(tmp_path):
    source = tmp_path / "legacy.db"
    slides = [{"index": 1, "title": "One", "bullets": [], "notes": "", "layout": "title"}]
    now = datetime.now(timezone.utc).isoformat()
    _legacy_database(
        source,
        [
            ("a-bad", "Bad", "sales", "minimalist", "16:9", json.dumps(slides), None, now, now),
            ("z-good", "Good", "sales", "minimalist", "16:9", json.dumps(slides), None, now, now),
        ],
    )
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'target.db'}")
    await database.create_schema()
    real = DeckRepository(database)

    class Repository(_GuardMixin):
        async def get_global(self, deck_id, *, session=None):
            return await real.get_global(deck_id)

        async def import_with_initial_version(self, **kwargs):
            if kwargs["deck_id"] == "a-bad":
                raise DeckWriteRolledBackError("rollback", RuntimeError("db"))
            return await real.import_with_initial_version(**kwargs)

    class Storage(LocalDeckFileStorage):
        async def delete(self, key):
            if "a-bad" in key:
                raise OSError("cleanup unavailable")
            await super().delete(key)

    try:
        result = await migrate_sqlite_decks(
            source, "owner", Repository(), Storage(tmp_path / "files"), template_path=None
        )
    finally:
        await database.dispose()

    assert (result.migrated, result.failed) == (1, 1)
    assert "compensation" in result.failures[0].reason


async def test_rollback_with_unavailable_reconciliation_preserves_uploaded_object(tmp_path):
    source = tmp_path / "legacy.db"
    slides = [{"index": 1, "title": "One", "bullets": [], "notes": "", "layout": "title"}]
    now = datetime.now(timezone.utc).isoformat()
    _legacy_database(
        source,
        [("legacy", "Deck", "sales", "minimalist", "16:9", json.dumps(slides), None, now, now)],
    )

    class Repository(_GuardMixin):
        lookups = 0

        async def get_global(self, deck_id, *, session=None):
            self.lookups += 1
            if self.lookups <= 2:
                return None
            raise OSError("database unavailable")

        async def import_with_initial_version(self, **kwargs):
            raise DeckWriteRolledBackError("rollback", RuntimeError("db"))

    class Storage:
        deleted = []

        async def put(self, key, content):
            return None

        async def delete(self, key):
            self.deleted.append(key)

    storage = Storage()
    result = await migrate_sqlite_decks(
        source, "owner", Repository(), storage, template_path=None
    )

    assert result.failed == 1
    assert "reconciliation failed" in result.failures[0].reason
    assert storage.deleted == []


@pytest.mark.parametrize("invalid_kind", ["oversized", "deep", "too-many"])
async def test_untrusted_legacy_input_is_bounded_before_rendering_and_next_row_continues(
    tmp_path, mocker, invalid_kind
):
    source = tmp_path / "legacy.db"
    good = [{"index": 1, "title": "Good", "bullets": [], "notes": "", "layout": "title"}]
    if invalid_kind == "oversized":
        bad = [{**good[0], "notes": "x" * 500}]
        limits = MigrationLimits(max_row_json_bytes=250)
    elif invalid_kind == "deep":
        bad = [{**good[0], "blocks": [{"nested": {"again": {"too": "deep"}}}]}]
        limits = MigrationLimits(max_json_depth=4)
    else:
        bad = good * 2
        limits = MigrationLimits(max_slides=1)
    now = datetime.now(timezone.utc).isoformat()
    _legacy_database(
        source,
        [
            ("a-bad", "Bad", "sales", "minimalist", "16:9", json.dumps(bad), None, now, now),
            ("z-good", "Good", "sales", "minimalist", "16:9", json.dumps(good), None, now, now),
        ],
    )
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'target.db'}")
    await database.create_schema()
    render = mocker.spy(__import__("scripts.migrate_sqlite_decks", fromlist=["PptxEngine"]).PptxEngine, "render")
    try:
        result = await migrate_sqlite_decks(
            source,
            "owner",
            DeckRepository(database),
            LocalDeckFileStorage(tmp_path / "files"),
            template_path=None,
            limits=limits,
        )
    finally:
        await database.dispose()

    assert (result.migrated, result.failed) == (1, 1)
    assert render.call_count == 1


def _large_png_b64() -> str:
    pixels = random.Random(42).randbytes(300 * 300 * 3)
    image = Image.frombytes("RGB", (300, 300), pixels)
    output = BytesIO()
    image.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


async def test_realistic_large_embedded_image_uses_image_budget_not_text_budget(tmp_path):
    source = tmp_path / "legacy.db"
    image_b64 = _large_png_b64()
    assert len(image_b64) > 200_000
    slides = [{
        "index": 1,
        "title": "Image",
        "bullets": [],
        "notes": "",
        "layout": "title",
        "image_b64": image_b64,
    }]
    now = datetime.now(timezone.utc).isoformat()
    _legacy_database(
        source,
        [("image", "Image", "sales", "minimalist", "16:9", json.dumps(slides), None, now, now)],
    )
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'target.db'}")
    await database.create_schema()
    try:
        result = await migrate_sqlite_decks(
            source,
            "owner",
            DeckRepository(database),
            LocalDeckFileStorage(tmp_path / "files"),
            template_path=None,
            limits=MigrationLimits(
                max_text_chars=100,
                max_total_text_chars=100,
                max_image_item_bytes=1_000_000,
                max_image_bytes=2_000_000,
            ),
        )
    finally:
        await database.dispose()

    assert (result.migrated, result.failed) == (1, 0)


def test_oversized_image_and_data_uri_use_decoded_image_limits():
    image_b64 = _large_png_b64()
    with pytest.raises(ValueError, match="embedded image"):
        _validate_decoded_budget(
            {"image_b64": image_b64},
            MigrationLimits(
                max_text_chars=10,
                max_total_text_chars=10,
                max_image_item_bytes=100_000,
            ),
        )

    _validate_decoded_budget(
        {"value": f"data:image/png;base64,{image_b64}"},
        MigrationLimits(
            max_text_chars=10,
            max_total_text_chars=10,
            max_image_item_bytes=1_000_000,
        ),
    )

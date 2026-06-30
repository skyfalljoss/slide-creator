import json
import sqlite3
from datetime import datetime, timezone
from io import BytesIO

from pptx import Presentation

from app.services.platform.database import Database
from app.services.platform.deck_files import LocalDeckFileStorage
from app.services.platform.deck_repository import DeckRepository
from app.services.platform.deck_repository import DeckWriteRolledBackError
from scripts.migrate_sqlite_decks import migrate_sqlite_decks


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

    class Repository:
        def __init__(self, error):
            self.error = error

        async def contains_deck_id(self, deck_id):
            return False

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

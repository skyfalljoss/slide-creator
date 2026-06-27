import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.services.platform.database import Database
from app.services.platform.deck_models import DeckVersionRow


async def test_database_creates_parent_and_enables_foreign_keys(tmp_path):
    database_path = tmp_path / "missing" / "deck_versions.db"
    database = Database(f"sqlite+aiosqlite:///{database_path}")

    try:
        await database.create_schema()
        async with database.session() as session:
            foreign_keys = (await session.execute(text("PRAGMA foreign_keys"))).scalar_one()
    finally:
        await database.dispose()

    assert database_path.exists()
    assert foreign_keys == 1


async def test_database_rejects_invalid_foreign_key(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'deck_versions.db'}")
    await database.create_schema()

    try:
        async with database.session() as session:
            session.add(
                DeckVersionRow(
                    id="version-id",
                    deck_id="missing-deck-id",
                    version_number=1,
                    storage_key="decks/missing/version.pptx",
                    sha256="0" * 64,
                    size_bytes=1,
                    source="generated",
                    created_by="test-user",
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
    finally:
        await database.dispose()


@pytest.mark.parametrize(
    "url",
    [
        "sqlite+aiosqlite:///:memory:",
        "sqlite+aiosqlite:///file:deck_versions?mode=memory&cache=shared&uri=true",
    ],
)
async def test_database_does_not_create_directory_for_non_file_sqlite(url, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    database = Database(url)

    try:
        await database.create_schema()
    finally:
        await database.dispose()

    assert list(tmp_path.iterdir()) == []

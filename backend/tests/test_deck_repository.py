import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform.database import Database
from app.services.platform.deck_models import DeckRow, DeckVersionRow
from app.services.platform.deck_repository import (
    DeckCommitUncertainError,
    DeckRepository,
    DeckWriteRolledBackError,
    _owned_deck_for_write,
)


@pytest.fixture
async def repository(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'decks.db'}")
    await database.create_schema()
    try:
        yield DeckRepository(database), database
    finally:
        await database.dispose()


@pytest.fixture
async def independent_repositories(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'concurrent-decks.db'}"
    first_database = Database(url)
    second_database = Database(url)
    await first_database.create_schema()
    try:
        yield DeckRepository(first_database), DeckRepository(second_database)
    finally:
        await first_database.dispose()
        await second_database.dispose()


async def create_deck(
    repository: DeckRepository,
    *,
    deck_id: str = "deck-1",
    version_id: str = "version-1",
    owner_id: str = "owner-1",
    name: str = "Quarterly Review",
    deck_type: str = "sales",
    generation_payload: dict | None = None,
):
    return await repository.create_with_initial_version(
        deck_id=deck_id,
        version_id=version_id,
        owner_id=owner_id,
        name=name,
        deck_type=deck_type,
        theme="citi",
        aspect_ratio="16:9",
        generation_payload=generation_payload,
        storage_key=f"decks/{deck_id}/{version_id}.pptx",
        sha256="a" * 64,
        size_bytes=123,
    )


def test_owned_deck_write_query_locks_on_postgresql_only():
    # Live PostgreSQL append-vs-delete integration remains an opt-in Task 13 test.
    postgres_query = str(
        _owned_deck_for_write("deck-1", "owner-1", "postgresql").compile(
            dialect=postgresql.dialect()
        )
    )
    sqlite_query = str(
        _owned_deck_for_write("deck-1", "owner-1", "sqlite").compile(
            dialect=sqlite.dialect()
        )
    )

    assert "FOR UPDATE" in postgres_query
    assert "FOR UPDATE" not in sqlite_query


async def test_create_with_initial_version_sets_current_version_atomically(repository):
    repo, _database = repository

    deck = await create_deck(
        repo,
        generation_payload={"slides": [{"title": "One"}]},
    )

    assert deck.id == "deck-1"
    assert deck.owner_id == "owner-1"
    assert deck.current_version_id == "version-1"
    assert deck.current_version is not None
    assert deck.current_version.version_number == 1
    assert deck.current_version.source == "generated"
    assert deck.current_version.created_by == "owner-1"
    assert deck.created_at.tzinfo is not None
    assert deck.current_version.created_at.tzinfo is not None
    assert await repo.get("deck-1", "owner-1") == deck


async def test_import_initial_version_preserves_timestamps_and_global_id_visibility(repository):
    repo, _database = repository
    created = datetime(2020, 1, 2, 3, 4, tzinfo=timezone.utc)
    updated = datetime(2021, 2, 3, 4, 5, tzinfo=timezone.utc)

    deck = await repo.import_with_initial_version(
        deck_id="legacy-id",
        version_id="legacy-version",
        owner_id="migration-owner",
        name="Legacy",
        deck_type="sales",
        theme="dark",
        aspect_ratio="4:3",
        generation_payload={"slides": []},
        storage_key="decks/legacy-id/versions/legacy-version.pptx",
        sha256="b" * 64,
        size_bytes=321,
        created_at=created,
        updated_at=updated,
    )

    assert deck.created_at == created
    assert deck.updated_at == updated
    assert deck.current_version.created_at == created
    assert await repo.contains_deck_id("legacy-id") is True
    assert await repo.get("legacy-id", "someone-else") is None


async def test_owner_scopes_user_facing_queries_and_mutations(repository):
    repo, _database = repository
    await create_deck(repo)

    assert await repo.get("deck-1", "other-owner") is None
    assert await repo.version("deck-1", "version-1", "other-owner") is None
    assert await repo.rename("deck-1", "other-owner", "Leaked") is False
    assert await repo.delete("deck-1", "other-owner") == []
    assert await repo.list_versions("deck-1", "other-owner") == []
    assert await repo.list_all("other-owner") == []
    assert (await repo.get("deck-1", "owner-1")).name == "Quarterly Review"


async def test_corrupt_cross_deck_current_pointer_does_not_expose_other_version(repository):
    repo, database = repository
    await create_deck(repo)
    await create_deck(
        repo,
        deck_id="deck-2",
        version_id="deck-2-v1",
        owner_id="owner-1",
        name="Other Deck",
    )
    async with database.session() as session, session.begin():
        await session.execute(
            update(DeckRow)
            .where(DeckRow.id == "deck-1")
            .values(current_version_id="deck-2-v1")
        )

    deck = await repo.get("deck-1", "owner-1")
    summary = (await repo.list_all("owner-1", search="Quarterly Review"))[0]

    assert deck is not None
    assert deck.current_version is None
    assert summary.current_version_number is None


async def test_list_all_filters_sorts_pages_and_counts_slides_safely(repository):
    repo, database = repository
    await create_deck(
        repo,
        deck_id="alpha",
        version_id="alpha-v1",
        name="Alpha Plan",
        deck_type="sales",
        generation_payload={"slides": [{}, {}]},
    )
    await create_deck(
        repo,
        deck_id="beta",
        version_id="beta-v1",
        name="beta plan",
        deck_type="strategy",
        generation_payload={"slides": "invalid"},
    )
    await create_deck(
        repo,
        deck_id="gamma",
        version_id="gamma-v1",
        name="Gamma",
        deck_type="sales",
        generation_payload=None,
    )
    now = datetime.now(timezone.utc)
    async with database.session() as session, session.begin():
        await session.execute(
            update(DeckRow)
            .where(DeckRow.id == "alpha")
            .values(created_at=now - timedelta(days=2), updated_at=now - timedelta(days=2))
        )
        await session.execute(
            update(DeckRow)
            .where(DeckRow.id == "beta")
            .values(created_at=now - timedelta(days=1), updated_at=now - timedelta(days=1))
        )
        await session.execute(
            update(DeckRow).where(DeckRow.id == "gamma").values(created_at=now, updated_at=now)
        )

    assert [item.id for item in await repo.list_all("owner-1")] == ["gamma", "beta", "alpha"]
    assert [item.id for item in await repo.list_all("owner-1", sort="oldest")] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert [item.id for item in await repo.list_all("owner-1", sort="name")] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert [item.id for item in await repo.list_all("owner-1", search="ALPHA")] == ["alpha"]
    assert [item.id for item in await repo.list_all("owner-1", deck_type="sales")] == [
        "gamma",
        "alpha",
    ]
    page = await repo.list_all("owner-1", sort="oldest", limit=1, offset=1)
    assert [item.id for item in page] == ["beta"]
    summaries = {item.id: item for item in await repo.list_all("owner-1")}
    assert summaries["alpha"].slide_count == 2
    assert summaries["beta"].slide_count == 0
    assert summaries["gamma"].slide_count == 0
    assert summaries["alpha"].current_version_number == 1
    assert not hasattr(summaries["alpha"], "storage_key")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit"),
        ({"limit": 101}, "limit"),
        ({"offset": -1}, "offset"),
        ({"sort": "recent"}, "sort"),
    ],
)
async def test_list_all_validates_pagination_and_sort(repository, kwargs, message):
    repo, _database = repository
    with pytest.raises(ValueError, match=message):
        await repo.list_all("owner-1", **kwargs)


async def test_rename_updates_owner_scoped_deck(repository):
    repo, _database = repository
    original = await create_deck(repo)

    assert await repo.rename("deck-1", "owner-1", "Renamed") is True
    renamed = await repo.get("deck-1", "owner-1")
    assert renamed.name == "Renamed"
    assert renamed.updated_at >= original.updated_at
    assert await repo.rename("missing", "owner-1", "Nope") is False


async def test_delete_breaks_current_pointer_cascades_versions_and_returns_keys(repository):
    repo, database = repository
    await create_deck(repo)
    await repo.append_version(
        deck_id="deck-1",
        owner_id="owner-1",
        version_id="version-2",
        storage_key="decks/deck-1/version-2.pptx",
        sha256="b" * 64,
        size_bytes=456,
        source="edited",
        created_by="owner-1",
    )

    keys = await repo.delete("deck-1", "owner-1")

    assert set(keys) == {
        "decks/deck-1/version-1.pptx",
        "decks/deck-1/version-2.pptx",
    }
    assert await repo.get("deck-1", "owner-1") is None
    async with database.session() as session:
        count = await session.scalar(
            select(func.count()).select_from(DeckVersionRow).where(DeckVersionRow.deck_id == "deck-1")
        )
    assert count == 0


async def test_append_lists_and_looks_up_monotonic_versions(repository):
    repo, _database = repository
    await create_deck(repo, generation_payload={"slides": [{}]})

    second = await repo.append_version(
        deck_id="deck-1",
        owner_id="owner-1",
        version_id="version-2",
        storage_key="decks/deck-1/version-2.pptx",
        sha256="b" * 64,
        size_bytes=456,
        source="edited",
        created_by="editor-1",
        base_version_id="version-1",
        generation_payload={"slides": [{}, {}, {}]},
    )
    third = await repo.append_version(
        deck_id="deck-1",
        owner_id="owner-1",
        version_id="version-3",
        storage_key="decks/deck-1/version-3.pptx",
        sha256="c" * 64,
        size_bytes=789,
        source="edited",
        created_by="editor-2",
    )

    assert second.version_number == 2
    assert third.version_number == 3
    assert [item.id for item in await repo.list_versions("deck-1", "owner-1")] == [
        "version-3",
        "version-2",
        "version-1",
    ]
    assert await repo.version("deck-1", "version-2", "owner-1") == second
    deck = await repo.get("deck-1", "owner-1")
    assert deck.current_version_id == "version-3"
    assert deck.current_version == third
    assert deck.generation_payload == {"slides": [{}, {}, {}]}


async def test_stale_base_still_appends_distinct_current_version(repository):
    repo, _database = repository
    await create_deck(repo)
    await repo.append_version(
        deck_id="deck-1",
        owner_id="owner-1",
        version_id="version-2",
        storage_key="decks/deck-1/version-2.pptx",
        sha256="b" * 64,
        size_bytes=2,
        source="edited",
        created_by="owner-1",
    )

    stale = await repo.append_version(
        deck_id="deck-1",
        owner_id="owner-1",
        version_id="version-stale",
        storage_key="decks/deck-1/version-stale.pptx",
        sha256="c" * 64,
        size_bytes=3,
        source="edited",
        created_by="owner-1",
        base_version_id="version-1",
    )

    assert stale.version_number == 3
    assert (await repo.get("deck-1", "owner-1")).current_version_id == "version-stale"


async def test_concurrent_sqlite_appends_allocate_distinct_versions(
    independent_repositories,
    monkeypatch,
):
    first_repo, second_repo = independent_repositories
    await create_deck(first_repo)

    first_at_max = asyncio.Event()
    second_at_max = asyncio.Event()
    release_first = asyncio.Event()
    original_scalar = AsyncSession.scalar

    async def pause_allocator(self, statement, *args, **kwargs):
        result = await original_scalar(self, statement, *args, **kwargs)
        if "max(deck_versions.version_number)" in str(statement).lower():
            if asyncio.current_task().get_name() == "append-first":
                first_at_max.set()
                await release_first.wait()
            else:
                second_at_max.set()
        return result

    monkeypatch.setattr(AsyncSession, "scalar", pause_allocator)
    first_task = asyncio.create_task(
        first_repo.append_version(
            deck_id="deck-1",
            owner_id="owner-1",
            version_id="version-a",
            storage_key="decks/deck-1/version-a.pptx",
            sha256="b" * 64,
            size_bytes=2,
            source="edited",
            created_by="owner-1",
        ),
        name="append-first",
    )
    await asyncio.wait_for(first_at_max.wait(), timeout=1)
    second_task = asyncio.create_task(
        second_repo.append_version(
            deck_id="deck-1",
            owner_id="owner-1",
            version_id="version-b",
            storage_key="decks/deck-1/version-b.pptx",
            sha256="c" * 64,
            size_bytes=3,
            source="edited",
            created_by="owner-1",
        ),
        name="append-second",
    )
    try:
        await asyncio.wait_for(second_at_max.wait(), timeout=0.05)
    except TimeoutError:
        pass
    finally:
        release_first.set()

    first, second = await asyncio.gather(first_task, second_task)
    assert sorted([first.version_number, second.version_number]) == [2, 3]
    assert [
        version.version_number
        for version in await first_repo.list_versions("deck-1", "owner-1")
    ] == [
        3,
        2,
        1,
    ]


async def test_concurrent_sqlite_append_and_delete_have_consistent_outcome(
    independent_repositories,
    monkeypatch,
):
    append_repo, delete_repo = independent_repositories
    await create_deck(append_repo)
    appended_key = "decks/deck-1/version-racing.pptx"
    delete_read_keys = asyncio.Event()
    release_delete = asyncio.Event()
    original_scalars = AsyncSession.scalars

    async def pause_delete_after_key_snapshot(self, statement, *args, **kwargs):
        result = await original_scalars(self, statement, *args, **kwargs)
        if (
            asyncio.current_task().get_name() == "delete-deck"
            and "deck_versions.storage_key" in str(statement).lower()
        ):
            delete_read_keys.set()
            await release_delete.wait()
        return result

    monkeypatch.setattr(AsyncSession, "scalars", pause_delete_after_key_snapshot)

    async def append():
        try:
            return await append_repo.append_version(
                deck_id="deck-1",
                owner_id="owner-1",
                version_id="version-racing",
                storage_key=appended_key,
                sha256="d" * 64,
                size_bytes=4,
                source="edited",
                created_by="owner-1",
            )
        except (LookupError, DeckWriteRolledBackError):
            return None

    delete_task = asyncio.create_task(
        delete_repo.delete("deck-1", "owner-1"),
        name="delete-deck",
    )
    await asyncio.wait_for(delete_read_keys.wait(), timeout=1)
    append_task = asyncio.create_task(append(), name="append-version")
    await asyncio.sleep(0.05)
    release_delete.set()
    appended, deleted_keys = await asyncio.gather(append_task, delete_task)

    if appended is None:
        assert deleted_keys == ["decks/deck-1/version-1.pptx"]
    else:
        assert appended_key in deleted_keys
    assert await append_repo.get("deck-1", "owner-1") is None


async def test_sqlite_append_commits_before_waiting_delete_returns_appended_key(
    independent_repositories,
    monkeypatch,
):
    append_repo, delete_repo = independent_repositories
    await create_deck(append_repo)
    appended_key = "decks/deck-1/version-appended-first.pptx"
    append_flushed = asyncio.Event()
    delete_attempted_begin = asyncio.Event()
    release_append = asyncio.Event()
    original_flush = AsyncSession.flush

    async def pause_append_after_flush(self, *args, **kwargs):
        await original_flush(self, *args, **kwargs)
        if asyncio.current_task().get_name() == "append-first":
            append_flushed.set()
            await release_append.wait()

    def notice_delete_begin(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            delete_attempted_begin.set()

    monkeypatch.setattr(AsyncSession, "flush", pause_append_after_flush)
    delete_engine = delete_repo._database.engine.sync_engine
    event.listen(delete_engine, "before_cursor_execute", notice_delete_begin)
    try:
        append_task = asyncio.create_task(
            append_repo.append_version(
                deck_id="deck-1",
                owner_id="owner-1",
                version_id="version-appended-first",
                storage_key=appended_key,
                sha256="e" * 64,
                size_bytes=5,
                source="edited",
                created_by="owner-1",
            ),
            name="append-first",
        )
        await asyncio.wait_for(append_flushed.wait(), timeout=1)
        delete_task = asyncio.create_task(
            delete_repo.delete("deck-1", "owner-1"),
            name="delete-second",
        )
        await asyncio.wait_for(delete_attempted_begin.wait(), timeout=1)
        release_append.set()
        appended, deleted_keys = await asyncio.gather(append_task, delete_task)
    finally:
        release_append.set()
        event.remove(delete_engine, "before_cursor_execute", notice_delete_begin)

    assert appended.storage_key == appended_key
    assert set(deleted_keys) == {
        "decks/deck-1/version-1.pptx",
        appended_key,
    }
    assert await append_repo.get("deck-1", "owner-1") is None
    assert await append_repo.all_storage_keys() == set()


async def test_append_missing_or_cross_owner_deck_returns_missing(repository):
    repo, _database = repository
    await create_deck(repo)

    with pytest.raises(DeckWriteRolledBackError) as raised:
        await repo.append_version(
            deck_id="deck-1",
            owner_id="other-owner",
            version_id="version-2",
            storage_key="decks/deck-1/version-2.pptx",
            sha256="b" * 64,
            size_bytes=2,
            source="edited",
            created_by="other-owner",
        )

    assert isinstance(raised.value.cause, LookupError)
    assert "Deck not found" in str(raised.value.cause)


async def test_stale_versions_and_protected_row_deletion(repository):
    repo, _database = repository
    await create_deck(repo)
    for number in range(2, 5):
        await repo.append_version(
            deck_id="deck-1",
            owner_id="owner-1",
            version_id=f"version-{number}",
            storage_key=f"decks/deck-1/version-{number}.pptx",
            sha256=str(number) * 64,
            size_bytes=number,
            source="edited",
            created_by="owner-1",
        )

    stale = await repo.stale_versions("deck-1", keep=2)
    assert [item.id for item in stale] == ["version-2", "version-1"]
    with pytest.raises(ValueError, match="keep"):
        await repo.stale_versions("deck-1", keep=0)

    deleted = await repo.delete_version_rows(
        ["version-1", "version-2", "version-4"]
    )
    assert deleted == ["version-1", "version-2"]
    assert [item.id for item in await repo.list_versions("deck-1", "owner-1")] == [
        "version-4",
        "version-3",
    ]


async def test_delete_version_rows_reserves_sqlite_writer_before_reading(repository):
    repo, database = repository
    await create_deck(repo)
    statements = []

    def record_statement(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.strip().upper())

    event.listen(database.engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        await repo.delete_version_rows(["version-1"])
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", record_statement)

    assert statements[0] == "BEGIN IMMEDIATE"


async def test_all_storage_keys_spans_owners(repository):
    repo, _database = repository
    await create_deck(repo)
    await create_deck(
        repo,
        deck_id="deck-2",
        version_id="deck-2-v1",
        owner_id="owner-2",
    )

    assert await repo.all_storage_keys() == {
        "decks/deck-1/version-1.pptx",
        "decks/deck-2/deck-2-v1.pptx",
    }


async def test_create_rolls_back_deck_when_initial_version_is_not_unique(repository):
    repo, database = repository
    await create_deck(repo)

    with pytest.raises(DeckWriteRolledBackError) as raised:
        await create_deck(
            repo,
            deck_id="deck-2",
            version_id="version-1",
            owner_id="owner-2",
        )

    assert isinstance(raised.value.cause, IntegrityError)

    async with database.session() as session:
        assert await session.get(DeckRow, "deck-2") is None
        count = await session.scalar(
            select(func.count()).select_from(DeckVersionRow).where(DeckVersionRow.deck_id == "deck-2")
        )
    assert count == 0


async def test_create_rolls_back_deck_when_initial_version_data_is_invalid(repository):
    repo, database = repository

    with pytest.raises(DeckWriteRolledBackError) as raised:
        await repo.create_with_initial_version(
            deck_id="invalid-deck",
            version_id="invalid-version",
            owner_id="owner-1",
            name="Invalid",
            deck_type="sales",
            theme="citi",
            aspect_ratio="16:9",
            generation_payload=None,
            storage_key="decks/invalid/version.pptx",
            sha256="a" * 64,
            size_bytes=None,  # type: ignore[arg-type]
        )

    assert isinstance(raised.value.cause, IntegrityError)

    async with database.session() as session:
        assert await session.get(DeckRow, "invalid-deck") is None
        assert await session.get(DeckVersionRow, "invalid-version") is None


async def test_append_commit_failure_is_classified_uncertain(repository, monkeypatch):
    repo, _database = repository
    await create_deck(repo)
    commit_error = OSError("connection lost during commit")

    async def fail_commit(_session):
        raise commit_error

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)

    with pytest.raises(DeckCommitUncertainError) as raised:
        await repo.append_version(
            deck_id="deck-1",
            owner_id="owner-1",
            version_id="version-uncertain",
            storage_key="decks/deck-1/version-uncertain.pptx",
            sha256="b" * 64,
            size_bytes=2,
            source="edited",
            created_by="owner-1",
        )

    assert raised.value.cause is commit_error


async def test_append_cancellation_rolls_back_and_propagates(repository, monkeypatch):
    repo, _database = repository
    await create_deck(repo)
    rollback_calls = 0
    original_rollback = AsyncSession.rollback

    async def cancel_flush(_session, *args, **kwargs):
        raise asyncio.CancelledError()

    async def track_rollback(session):
        nonlocal rollback_calls
        rollback_calls += 1
        await original_rollback(session)

    monkeypatch.setattr(AsyncSession, "flush", cancel_flush)
    monkeypatch.setattr(AsyncSession, "rollback", track_rollback)

    with pytest.raises(asyncio.CancelledError):
        await repo.append_version(
            deck_id="deck-1",
            owner_id="owner-1",
            version_id="version-cancelled",
            storage_key="decks/deck-1/version-cancelled.pptx",
            sha256="c" * 64,
            size_bytes=3,
            source="edited",
            created_by="owner-1",
        )

    assert rollback_calls == 1


async def test_append_rollback_failure_is_classified_uncertain(repository, monkeypatch):
    repo, _database = repository
    await create_deck(repo)
    flush_error = RuntimeError("flush failed")

    async def fail_flush(_session, *args, **kwargs):
        raise flush_error

    async def fail_rollback(_session):
        raise OSError("rollback failed")

    monkeypatch.setattr(AsyncSession, "flush", fail_flush)
    monkeypatch.setattr(AsyncSession, "rollback", fail_rollback)

    with pytest.raises(DeckCommitUncertainError) as raised:
        await repo.append_version(
            deck_id="deck-1",
            owner_id="owner-1",
            version_id="version-rollback-unknown",
            storage_key="decks/deck-1/version-rollback-unknown.pptx",
            sha256="d" * 64,
            size_bytes=4,
            source="edited",
            created_by="owner-1",
        )

    assert raised.value.cause is flush_error

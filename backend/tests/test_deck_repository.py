from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.services.platform.database import Database
from app.services.platform.deck_models import DeckRow, DeckVersionRow
from app.services.platform.deck_repository import DeckRepository


@pytest.fixture
async def repository(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'decks.db'}")
    await database.create_schema()
    try:
        yield DeckRepository(database), database
    finally:
        await database.dispose()


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


async def test_append_missing_or_cross_owner_deck_returns_missing(repository):
    repo, _database = repository
    await create_deck(repo)

    with pytest.raises(LookupError, match="Deck not found"):
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

    await repo.delete_version_rows(["version-1", "version-2", "version-4"])
    assert [item.id for item in await repo.list_versions("deck-1", "owner-1")] == [
        "version-4",
        "version-3",
    ]


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

    with pytest.raises(IntegrityError):
        await create_deck(
            repo,
            deck_id="deck-2",
            version_id="version-1",
            owner_id="owner-2",
        )

    async with database.session() as session:
        assert await session.get(DeckRow, "deck-2") is None
        count = await session.scalar(
            select(func.count()).select_from(DeckVersionRow).where(DeckVersionRow.deck_id == "deck-2")
        )
    assert count == 0


async def test_create_rolls_back_deck_when_initial_version_data_is_invalid(repository):
    repo, database = repository

    with pytest.raises(IntegrityError):
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

    async with database.session() as session:
        assert await session.get(DeckRow, "invalid-deck") is None
        assert await session.get(DeckVersionRow, "invalid-version") is None

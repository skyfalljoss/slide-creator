from datetime import datetime, timedelta, timezone

from app.services.platform.deck_files import DeckFileObject
from scripts.cleanup_orphan_deck_files import cleanup_orphan_deck_files


class FakeRepository:
    def __init__(self, keys=None, error=None):
        self.keys = set(keys or ())
        self.error = error

    async def all_storage_keys(self):
        if self.error:
            raise self.error
        return self.keys

    async def storage_key_referenced(self, key):
        return key in self.keys


class FakeStorage:
    def __init__(self, objects=None, *, list_error=None, delete_error=None):
        self.objects = list(objects or ())
        self.list_error = list_error
        self.delete_error = delete_error
        self.deleted = []

    async def list_objects(self, prefix):
        assert prefix == "decks/"
        if self.list_error:
            raise self.list_error
        return self.objects

    async def delete(self, key):
        if key == self.delete_error:
            raise OSError("delete failed")
        self.deleted.append(key)


async def test_cleanup_defaults_to_dry_run_and_retains_exact_grace_boundary():
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    storage = FakeStorage(
        [
            DeckFileObject("decks/d/v1.pptx", now - timedelta(days=10)),
            DeckFileObject("decks/d/v2.pptx", now - timedelta(days=2)),
            DeckFileObject("decks/d/orphan.pptx", now - timedelta(hours=24)),
            DeckFileObject("decks/d/fresh.pptx", now - timedelta(hours=23)),
        ]
    )
    repository = FakeRepository({"decks/d/v1.pptx", "decks/d/v2.pptx"})

    result = await cleanup_orphan_deck_files(repository, storage, now=now)

    assert (result.examined, result.retained, result.candidates, result.deleted) == (4, 4, 0, 0)
    assert result.failed == 0
    assert storage.deleted == []


async def test_cleanup_apply_deletes_candidates_and_reports_each_failure():
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    storage = FakeStorage(
        [
            DeckFileObject("decks/d/a.pptx", now - timedelta(days=2)),
            DeckFileObject("decks/d/b.pptx", now - timedelta(days=2)),
        ],
        delete_error="decks/d/b.pptx",
    )

    result = await cleanup_orphan_deck_files(
        FakeRepository(), storage, apply=True, now=now
    )

    assert (result.candidates, result.deleted, result.failed) == (2, 1, 1)
    assert storage.deleted == ["decks/d/a.pptx"]


async def test_cleanup_rechecks_candidate_that_becomes_referenced_before_delete():
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    key = "decks/d/newly-referenced.pptx"
    storage = FakeStorage([DeckFileObject(key, now - timedelta(days=2))])

    class RacingRepository(FakeRepository):
        async def storage_key_referenced(self, candidate):
            self.keys.add(candidate)
            return True

    result = await cleanup_orphan_deck_files(
        RacingRepository(), storage, apply=True, now=now
    )

    assert result.deleted == 0
    assert result.retained == 1
    assert storage.deleted == []


async def test_cleanup_recheck_failure_is_fail_closed():
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    key = "decks/d/uncertain.pptx"
    storage = FakeStorage([DeckFileObject(key, now - timedelta(days=2))])

    class UnavailableRepository(FakeRepository):
        async def storage_key_referenced(self, candidate):
            raise OSError("database unavailable")

    result = await cleanup_orphan_deck_files(
        UnavailableRepository(), storage, apply=True, now=now
    )

    assert result.failed == 1 and result.retained == 1
    assert storage.deleted == []


async def test_cleanup_never_deletes_when_listing_or_repository_is_uncertain():
    now = datetime.now(timezone.utc)
    old = [DeckFileObject("decks/d/orphan.pptx", now - timedelta(days=2))]
    metadata_failure = FakeStorage(old)
    metadata_failure.objects[0] = DeckFileObject("decks/d/orphan.pptx", None)
    repository_failure = FakeStorage(old)
    listing_failure = FakeStorage(old, list_error=OSError("listing incomplete"))

    missing_time = await cleanup_orphan_deck_files(
        FakeRepository(), metadata_failure, apply=True, now=now
    )
    missing_keys = await cleanup_orphan_deck_files(
        FakeRepository(error=OSError("database unavailable")),
        repository_failure,
        apply=True,
        now=now,
    )
    missing_list = await cleanup_orphan_deck_files(
        FakeRepository(), listing_failure, apply=True, now=now
    )

    assert missing_time.failed == 1 and metadata_failure.deleted == []
    assert missing_keys.failed == 1 and repository_failure.deleted == []
    assert missing_list.failed == 1 and listing_failure.deleted == []

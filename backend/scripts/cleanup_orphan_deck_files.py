"""Report or remove unreferenced immutable deck files after a grace period."""

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from app.config import settings
from app.services.platform.database import Database
from app.services.platform.deck_files import (
    DeckFileStorage,
    GCSDeckFileStorage,
    LocalDeckFileStorage,
    await_destructive,
)
from app.services.platform.deck_repository import DeckRepository


class StorageKeyRepository(Protocol):
    async def all_storage_keys(self) -> set[str]: ...
    async def storage_key_referenced(self, storage_key: str) -> bool: ...
    def storage_key_guard(self, storage_key: str): ...


@dataclass(frozen=True)
class CleanupResult:
    examined: int = 0
    retained: int = 0
    candidates: int = 0
    deleted: int = 0
    failed: int = 0
    failure_messages: tuple[str, ...] = ()


async def cleanup_orphan_deck_files(
    repository: StorageKeyRepository,
    storage: DeckFileStorage,
    *,
    apply: bool = False,
    grace_period: timedelta = timedelta(hours=24),
    now: datetime | None = None,
) -> CleanupResult:
    if grace_period < timedelta(0):
        raise ValueError("grace_period must be non-negative")
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    cutoff = current_time.astimezone(timezone.utc) - grace_period
    try:
        referenced = await repository.all_storage_keys()
        objects = await storage.list_objects("decks/")
    except Exception as exc:
        # A partial metadata snapshot could classify live objects as orphans.
        return CleanupResult(
            failed=1,
            failure_messages=(f"snapshot unavailable ({type(exc).__name__})",),
        )

    retained = candidates = deleted = failed = 0
    failures: list[str] = []
    for item in objects:
        modified = item.updated_at
        if item.key in referenced:
            retained += 1
        elif modified is None:
            retained += 1
            failed += 1
            failures.append(f"missing modified time: {item.key}")
        else:
            if modified.tzinfo is None:
                retained += 1
                failed += 1
                failures.append(f"invalid modified time: {item.key}")
                continue
            if modified.astimezone(timezone.utc) >= cutoff:
                retained += 1
                continue
            candidates += 1
            if apply:
                failure_phase = "guard/recheck"
                try:
                    guard = repository.storage_key_guard(item.key)
                    async with guard as guard_session:
                        referenced_now = await repository.storage_key_referenced(
                            item.key, session=guard_session
                        )
                        if referenced_now:
                            retained += 1
                            candidates -= 1
                            continue
                        failure_phase = "delete"
                        await await_destructive(storage.delete(item.key))
                        failure_phase = "guard/recheck"
                    deleted += 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    retained += 1
                    if failure_phase != "delete":
                        candidates -= 1
                    failed += 1
                    failures.append(
                        f"storage {failure_phase} failed "
                        f"({type(exc).__name__}): {item.key}"
                    )
    return CleanupResult(
        len(objects), retained, candidates, deleted, failed, tuple(failures)
    )


def _storage() -> DeckFileStorage:
    if settings.storage_provider == "gcs":
        return GCSDeckFileStorage(settings.gcs_bucket)
    return LocalDeckFileStorage(Path(settings.local_deck_file_dir))


async def _main(args: argparse.Namespace) -> int:
    database = Database(settings.database_url)
    storage = _storage()
    try:
        result = await cleanup_orphan_deck_files(
            DeckRepository(database, lock_dir=settings.deck_lock_dir),
            storage,
            apply=args.apply,
        )
    finally:
        await database.dispose()
        close = getattr(storage, "close", None)
        if close is not None:
            await close()
    mode = "apply" if args.apply else "dry-run"
    for message in result.failure_messages:
        print(message)
    print(
        f"mode={mode} examined={result.examined} retained={result.retained} "
        f"candidate={result.candidates} deleted={result.deleted} failed={result.failed}"
    )
    return 1 if result.failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="delete eligible objects")
    mode.add_argument("--dry-run", action="store_true", help="report only (default)")
    return asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

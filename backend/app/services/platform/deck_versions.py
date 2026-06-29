import asyncio
import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid4, uuid5

import structlog

from app.models.schemas import SlideData
from app.services.platform.deck_files import DeckFileStorage
from app.services.platform.deck_repository import (
    DeckRecord,
    DeckRepository,
    DeckVersionRecord,
    DeckWriteRolledBackError,
)
from app.services.presentation.pptx_engine import PptxEngine
from app.services.presentation.pptx_validation import validate_pptx


logger = structlog.get_logger(__name__)


class DeckVersionError(Exception):
    """Base error for stable deck-version service failures."""


class DeckNotFoundError(DeckVersionError, LookupError):
    """The requested deck or owned version does not exist."""


class VersionStorageConflictError(DeckVersionError):
    """An immutable object exists without matching committed metadata."""


@dataclass
class _LockEntry:
    lock: asyncio.Lock
    users: int = 0


class DeckVersionService:
    def __init__(
        self,
        repository: DeckRepository,
        storage: DeckFileStorage,
        sample_template_path: str | None,
        max_file_bytes: int,
        retention: int,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._sample_template_path = sample_template_path
        self._max_file_bytes = max_file_bytes
        self._retention = retention
        self._lock_entries: dict[str, _LockEntry] = {}
        self._lock_entries_guard = asyncio.Lock()
        self._retry_delays = (0, 0.01, 0.05, 0.1, 0.25)
        self._sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    async def create_generated_deck(
        self,
        *,
        owner_id: str,
        name: str,
        deck_type: str,
        theme: str,
        aspect_ratio: str,
        slides: list[SlideData],
    ) -> DeckRecord:
        engine = PptxEngine(
            template_path=self._sample_template_path,
            theme=theme,
            aspect_ratio=aspect_ratio,
        )
        content = await asyncio.to_thread(engine.render, slides)
        checksum = await self._validate_and_hash(content)

        deck_id = str(uuid4())
        version_id = str(uuid4())
        storage_key = f"decks/{deck_id}/versions/{version_id}.pptx"
        await self._storage.put(storage_key, content)
        try:
            return await self._repository.create_with_initial_version(
                deck_id=deck_id,
                version_id=version_id,
                owner_id=owner_id,
                name=name,
                deck_type=deck_type,
                theme=theme,
                aspect_ratio=aspect_ratio,
                generation_payload={
                    "slides": [item.model_dump(mode="json") for item in slides]
                },
                storage_key=storage_key,
                sha256=checksum,
                size_bytes=len(content),
            )
        except asyncio.CancelledError:
            raise
        except DeckWriteRolledBackError:
            await self._delete_failed_upload(
                deck_id=deck_id,
                version_id=version_id,
                storage_key=storage_key,
            )
            raise
        except Exception as repository_error:
            return await self._reconcile_initial_exception(
                repository_error=repository_error,
                deck_id=deck_id,
                version_id=version_id,
                owner_id=owner_id,
                storage_key=storage_key,
                checksum=checksum,
            )

    async def save_edited_version(
        self,
        *,
        deck_id: str,
        owner_id: str,
        content: bytes,
        base_version_id: str,
        callback_key: str,
        created_by: str,
    ) -> DeckVersionRecord:
        checksum = await self._validate_and_hash(content)
        version_id = str(
            uuid5(NAMESPACE_URL, f"slideforge:{deck_id}:{callback_key}:{checksum}")
        )
        storage_key = f"decks/{deck_id}/versions/{version_id}.pptx"

        async with self._coordinate(version_id):
            existing = await self._repository.version(deck_id, version_id, owner_id)
            if existing is not None:
                result = self._matching_version(existing, checksum)
                await self._enforce_retention(deck_id)
                return result
            if await self._repository.get(deck_id, owner_id) is None:
                raise DeckNotFoundError("Deck not found")

            try:
                await self._storage.put(storage_key, content)
            except FileExistsError:
                result = await self._resolve_existing_version(
                    deck_id=deck_id,
                    version_id=version_id,
                    owner_id=owner_id,
                    checksum=checksum,
                    base_version_id=base_version_id,
                    created_by=created_by,
                    content_size=len(content),
                    storage_key=storage_key,
                )
            else:
                try:
                    result = await self._repository.append_version(
                        deck_id=deck_id,
                        owner_id=owner_id,
                        version_id=version_id,
                        storage_key=storage_key,
                        sha256=checksum,
                        size_bytes=len(content),
                        source="onlyoffice_save",
                        created_by=created_by,
                        base_version_id=base_version_id,
                    )
                except asyncio.CancelledError:
                    raise
                except DeckWriteRolledBackError:
                    await self._delete_failed_upload(
                        deck_id=deck_id,
                        version_id=version_id,
                        storage_key=storage_key,
                    )
                    raise
                except Exception as repository_error:
                    result = await self._reconcile_append_exception(
                        repository_error=repository_error,
                        deck_id=deck_id,
                        version_id=version_id,
                        owner_id=owner_id,
                        storage_key=storage_key,
                        checksum=checksum,
                    )
            await self._enforce_retention(deck_id)
            return result

    async def restore_version(
        self,
        *,
        deck_id: str,
        version_id: str,
        owner_id: str,
        created_by: str,
    ) -> DeckVersionRecord:
        deck = await self._repository.get(deck_id, owner_id)
        if deck is None or deck.current_version is None:
            raise DeckNotFoundError("Deck not found")
        selected = await self._repository.version(deck_id, version_id, owner_id)
        if selected is None:
            raise DeckNotFoundError("Deck version not found")
        content = await self._storage.read(selected.storage_key)
        return await self._append_content(
            deck_id=deck_id,
            owner_id=owner_id,
            content=content,
            source="restore",
            created_by=created_by,
            base_version_id=deck.current_version.id,
        )

    async def save_slides_as_version(
        self,
        *,
        deck_id: str,
        owner_id: str,
        slides: list[SlideData],
        theme: str,
        aspect_ratio: str,
        created_by: str,
        name: str | None = None,
    ) -> DeckVersionRecord:
        deck = await self._repository.get(deck_id, owner_id)
        if deck is None or deck.current_version is None:
            raise DeckNotFoundError("Deck not found")
        engine = PptxEngine(
            template_path=self._sample_template_path,
            theme=theme,
            aspect_ratio=aspect_ratio,
        )
        content = await asyncio.to_thread(engine.render, slides)
        return await self._append_content(
            deck_id=deck_id,
            owner_id=owner_id,
            content=content,
            source="generated",
            created_by=created_by,
            base_version_id=deck.current_version.id,
            generation_payload={
                "slides": [item.model_dump(mode="json") for item in slides]
            },
            name=name,
        )

    async def _append_content(
        self,
        *,
        deck_id: str,
        owner_id: str,
        content: bytes,
        source: str,
        created_by: str,
        base_version_id: str,
        generation_payload: dict | None = None,
        name: str | None = None,
    ) -> DeckVersionRecord:
        checksum = await self._validate_and_hash(content)
        version_id = str(uuid4())
        storage_key = f"decks/{deck_id}/versions/{version_id}.pptx"
        await self._storage.put(storage_key, content)
        try:
            result = await self._repository.append_version(
                deck_id=deck_id,
                owner_id=owner_id,
                version_id=version_id,
                storage_key=storage_key,
                sha256=checksum,
                size_bytes=len(content),
                source=source,
                created_by=created_by,
                base_version_id=base_version_id,
                generation_payload=generation_payload,
                name=name,
            )
        except asyncio.CancelledError:
            raise
        except DeckWriteRolledBackError:
            await self._delete_failed_upload(
                deck_id=deck_id,
                version_id=version_id,
                storage_key=storage_key,
            )
            raise
        except Exception as repository_error:
            result = await self._reconcile_append_exception(
                repository_error=repository_error,
                deck_id=deck_id,
                version_id=version_id,
                owner_id=owner_id,
                storage_key=storage_key,
                checksum=checksum,
            )
        await self._enforce_retention(deck_id)
        return result

    async def _reconcile_initial_exception(
        self,
        *,
        repository_error: BaseException,
        deck_id: str,
        version_id: str,
        owner_id: str,
        storage_key: str,
        checksum: str,
    ) -> DeckRecord:
        try:
            deck = await self._repository.get(deck_id, owner_id)
        except Exception:
            logger.exception(
                "deck_initial_version_reconciliation_failed",
                deck_id=deck_id,
                version_id=version_id,
                storage_key=storage_key,
            )
            raise repository_error
        if deck is None:
            raise repository_error
        current = deck.current_version
        if (
            deck.current_version_id != version_id
            or current is None
            or current.id != version_id
            or current.storage_key != storage_key
            or current.sha256 != checksum
        ):
            raise VersionStorageConflictError(
                "Initial version metadata does not match immutable storage identity"
            )
        return deck

    async def _reconcile_append_exception(
        self,
        *,
        repository_error: BaseException,
        deck_id: str,
        version_id: str,
        owner_id: str,
        storage_key: str,
        checksum: str,
    ) -> DeckVersionRecord:
        try:
            existing = await self._repository.version(deck_id, version_id, owner_id)
        except Exception:
            logger.exception(
                "deck_version_reconciliation_failed",
                deck_id=deck_id,
                version_id=version_id,
                storage_key=storage_key,
            )
            raise repository_error
        if existing is None:
            raise repository_error
        if existing.storage_key != storage_key:
            raise VersionStorageConflictError(
                "Version metadata storage key does not match immutable storage identity"
            )
        return self._matching_version(existing, checksum)

    async def _enforce_retention(self, deck_id: str) -> None:
        try:
            stale_versions = await self._repository.stale_versions(
                deck_id, self._retention
            )
        except Exception:
            logger.exception("deck_version_retention_query_failed", deck_id=deck_id)
            return

        if not stale_versions:
            return
        try:
            deleted_ids = await self._repository.delete_version_rows(
                [version.id for version in stale_versions]
            )
        except Exception as exc:
            logger.warning(
                "deck_version_retention_row_delete_failed",
                deck_id=deck_id,
                failure_type=type(exc).__name__,
            )
            return

        deleted = set(deleted_ids)
        for version in stale_versions:
            if version.id not in deleted:
                continue
            try:
                await self._storage.delete(version.storage_key)
            except Exception as exc:
                logger.warning(
                    "deck_version_retention_object_delete_failed",
                    deck_id=deck_id,
                    version_id=version.id,
                    failure_type=type(exc).__name__,
                )

    async def _resolve_existing_version(
        self,
        *,
        deck_id: str,
        version_id: str,
        owner_id: str,
        checksum: str,
        base_version_id: str,
        created_by: str,
        content_size: int,
        storage_key: str,
    ) -> DeckVersionRecord:
        for retry_delay in self._retry_delays:
            await self._sleep(retry_delay)
            existing = await self._repository.version(deck_id, version_id, owner_id)
            if existing is not None:
                return self._matching_stored_version(
                    existing, checksum=checksum, storage_key=storage_key
                )

        stored_content = await self._storage.read(storage_key)
        stored_checksum = await self._validate_and_hash(stored_content)
        if stored_checksum != checksum:
            raise VersionStorageConflictError(
                "Immutable storage object checksum does not match requested version"
            )
        try:
            return await self._repository.append_version(
                deck_id=deck_id,
                owner_id=owner_id,
                version_id=version_id,
                storage_key=storage_key,
                sha256=checksum,
                size_bytes=content_size,
                source="onlyoffice_save",
                created_by=created_by,
                base_version_id=base_version_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception as repair_error:
            try:
                existing = await self._repository.version(
                    deck_id, version_id, owner_id
                )
            except Exception as reconciliation_error:
                raise VersionStorageConflictError(
                    "Version orphan repair outcome could not be reconciled"
                ) from reconciliation_error
            if existing is not None:
                return self._matching_stored_version(
                    existing, checksum=checksum, storage_key=storage_key
                )
            raise VersionStorageConflictError(
                "Version storage orphan could not be repaired"
            ) from repair_error

    @staticmethod
    def _matching_stored_version(
        existing: DeckVersionRecord, *, checksum: str, storage_key: str
    ) -> DeckVersionRecord:
        if existing.storage_key != storage_key:
            raise VersionStorageConflictError(
                "Version metadata storage key does not match immutable storage identity"
            )
        return DeckVersionService._matching_version(existing, checksum)

    async def _validate_and_hash(self, content: bytes) -> str:
        def validate_and_hash() -> str:
            validate_pptx(content, max_bytes=self._max_file_bytes)
            return hashlib.sha256(content).hexdigest()

        return await asyncio.to_thread(validate_and_hash)

    @asynccontextmanager
    async def _coordinate(self, version_id: str) -> AsyncIterator[None]:
        async with self._lock_entries_guard:
            entry = self._lock_entries.get(version_id)
            if entry is None:
                entry = _LockEntry(lock=asyncio.Lock())
                self._lock_entries[version_id] = entry
            entry.users += 1
        acquired = False
        try:
            await entry.lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                entry.lock.release()
            async with self._lock_entries_guard:
                entry.users -= 1
                if entry.users == 0:
                    self._lock_entries.pop(version_id, None)

    @staticmethod
    def _matching_version(
        existing: DeckVersionRecord, checksum: str
    ) -> DeckVersionRecord:
        if existing.sha256 != checksum:
            raise VersionStorageConflictError(
                "Version metadata checksum does not match immutable storage identity"
            )
        return existing

    async def _delete_failed_upload(
        self,
        *,
        deck_id: str,
        version_id: str,
        storage_key: str,
    ) -> None:
        try:
            await self._storage.delete(storage_key)
        except Exception:
            logger.exception(
                "deck_version_cleanup_failed",
                deck_id=deck_id,
                version_id=version_id,
                storage_key=storage_key,
            )

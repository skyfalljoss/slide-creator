import asyncio
import hashlib
from uuid import NAMESPACE_URL, uuid4, uuid5

import structlog

from app.models.schemas import SlideData
from app.services.platform.deck_files import DeckFileStorage
from app.services.platform.deck_repository import DeckRecord, DeckRepository, DeckVersionRecord
from app.services.presentation.pptx_engine import PptxEngine
from app.services.presentation.pptx_validation import validate_pptx


logger = structlog.get_logger(__name__)


class VersionStorageConflictError(RuntimeError):
    """An immutable object exists without matching committed metadata."""


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
        self._editor_save_lock = asyncio.Lock()

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
        validate_pptx(content, max_bytes=self._max_file_bytes)

        deck_id = str(uuid4())
        version_id = str(uuid4())
        storage_key = f"decks/{deck_id}/versions/{version_id}.pptx"
        checksum = hashlib.sha256(content).hexdigest()
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
        except BaseException:
            try:
                await self._storage.delete(storage_key)
            except Exception:
                logger.exception(
                    "deck_initial_version_cleanup_failed",
                    deck_id=deck_id,
                    version_id=version_id,
                    storage_key=storage_key,
                )
            raise

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
        validate_pptx(content, max_bytes=self._max_file_bytes)
        checksum = hashlib.sha256(content).hexdigest()
        version_id = str(
            uuid5(NAMESPACE_URL, f"slideforge:{deck_id}:{callback_key}:{checksum}")
        )
        storage_key = f"decks/{deck_id}/versions/{version_id}.pptx"

        async with self._editor_save_lock:
            existing = await self._repository.version(deck_id, version_id, owner_id)
            if existing is not None:
                return self._matching_version(existing, checksum)
            if await self._repository.get(deck_id, owner_id) is None:
                raise LookupError("Deck not found")

            try:
                await self._storage.put(storage_key, content)
            except FileExistsError:
                return await self._resolve_existing_version(
                    deck_id=deck_id,
                    version_id=version_id,
                    owner_id=owner_id,
                    checksum=checksum,
                )

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
            except BaseException:
                await self._delete_failed_upload(
                    deck_id=deck_id,
                    version_id=version_id,
                    storage_key=storage_key,
                )
                raise
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
            raise LookupError("Deck not found")
        selected = await self._repository.version(deck_id, version_id, owner_id)
        if selected is None:
            raise LookupError("Deck version not found")
        content = await self._storage.read(selected.storage_key)
        validate_pptx(content, max_bytes=self._max_file_bytes)
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
    ) -> DeckVersionRecord:
        deck = await self._repository.get(deck_id, owner_id)
        if deck is None or deck.current_version is None:
            raise LookupError("Deck not found")
        engine = PptxEngine(
            template_path=self._sample_template_path,
            theme=theme,
            aspect_ratio=aspect_ratio,
        )
        content = await asyncio.to_thread(engine.render, slides)
        validate_pptx(content, max_bytes=self._max_file_bytes)
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
    ) -> DeckVersionRecord:
        validate_pptx(content, max_bytes=self._max_file_bytes)
        version_id = str(uuid4())
        storage_key = f"decks/{deck_id}/versions/{version_id}.pptx"
        checksum = hashlib.sha256(content).hexdigest()
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
            )
        except BaseException:
            await self._delete_failed_upload(
                deck_id=deck_id,
                version_id=version_id,
                storage_key=storage_key,
            )
            raise
        await self._enforce_retention(deck_id)
        return result

    async def _enforce_retention(self, deck_id: str) -> None:
        try:
            stale_versions = await self._repository.stale_versions(
                deck_id, self._retention
            )
        except Exception:
            logger.exception("deck_version_retention_query_failed", deck_id=deck_id)
            return

        deleted_ids: list[str] = []
        for version in stale_versions:
            try:
                await self._storage.delete(version.storage_key)
            except Exception:
                logger.exception(
                    "deck_version_retention_object_delete_failed",
                    deck_id=deck_id,
                    version_id=version.id,
                    storage_key=version.storage_key,
                )
            else:
                deleted_ids.append(version.id)

        if not deleted_ids:
            return
        try:
            await self._repository.delete_version_rows(deleted_ids)
        except Exception:
            logger.exception(
                "deck_version_retention_row_delete_failed",
                deck_id=deck_id,
                version_ids=deleted_ids,
            )

    async def _resolve_existing_version(
        self,
        *,
        deck_id: str,
        version_id: str,
        owner_id: str,
        checksum: str,
    ) -> DeckVersionRecord:
        for retry_delay in (0, 0.01, 0.05):
            existing = await self._repository.version(deck_id, version_id, owner_id)
            if existing is not None:
                return self._matching_version(existing, checksum)
            await asyncio.sleep(retry_delay)
        raise VersionStorageConflictError(
            "Version storage object exists but matching metadata was not committed"
        )

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

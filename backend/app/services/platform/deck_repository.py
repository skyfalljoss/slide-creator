from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import delete as sqlalchemy_delete
from sqlalchemy import and_, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.services.platform.database import Database
from app.services.platform.deck_models import DeckRow, DeckVersionRow


logger = structlog.get_logger(__name__)


def _owned_deck_for_write(
    deck_id: str,
    owner_id: str,
    dialect_name: str,
) -> Select[tuple[DeckRow]]:
    statement = select(DeckRow).where(
        DeckRow.id == deck_id,
        DeckRow.owner_id == owner_id,
    )
    if dialect_name == "postgresql":
        statement = statement.with_for_update()
    return statement


@asynccontextmanager
async def _serialized_write(session: AsyncSession) -> AsyncIterator[None]:
    dialect_name = session.bind.dialect.name if session.bind is not None else ""
    if dialect_name == "sqlite":
        # Reserve SQLite's single writer before reading a version number or
        # deletion snapshot. This serializes across connections and processes.
        await session.execute(text("BEGIN IMMEDIATE"))
        try:
            yield
        except BaseException:
            await session.rollback()
            raise
        else:
            await session.commit()
        return

    async with session.begin():
        yield


@dataclass(frozen=True)
class DeckVersionRecord:
    id: str
    deck_id: str
    version_number: int
    storage_key: str
    sha256: str
    size_bytes: int
    source: str
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class DeckRecord:
    id: str
    owner_id: str
    name: str
    deck_type: str
    theme: str
    aspect_ratio: str
    generation_payload: dict | None
    current_version_id: str | None
    created_at: datetime
    updated_at: datetime
    current_version: DeckVersionRecord | None


@dataclass(frozen=True)
class DeckSummaryRecord:
    id: str
    name: str
    deck_type: str
    slide_count: int
    current_version_id: str | None
    current_version_number: int | None
    created_at: datetime
    updated_at: datetime


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _version_record(row: DeckVersionRow) -> DeckVersionRecord:
    return DeckVersionRecord(
        id=row.id,
        deck_id=row.deck_id,
        version_number=row.version_number,
        storage_key=row.storage_key,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        source=row.source,
        created_by=row.created_by,
        created_at=_utc(row.created_at),
    )


def _deck_record(deck: DeckRow, version: DeckVersionRow | None) -> DeckRecord:
    return DeckRecord(
        id=deck.id,
        owner_id=deck.owner_id,
        name=deck.name,
        deck_type=deck.deck_type,
        theme=deck.theme,
        aspect_ratio=deck.aspect_ratio,
        generation_payload=(
            deck.generation_payload if isinstance(deck.generation_payload, dict) else None
        ),
        current_version_id=deck.current_version_id,
        created_at=_utc(deck.created_at),
        updated_at=_utc(deck.updated_at),
        current_version=_version_record(version) if version is not None else None,
    )


class DeckRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create_with_initial_version(
        self,
        *,
        deck_id: str,
        version_id: str,
        owner_id: str,
        name: str,
        deck_type: str,
        theme: str,
        aspect_ratio: str,
        generation_payload: dict | None,
        storage_key: str,
        sha256: str,
        size_bytes: int,
    ) -> DeckRecord:
        now = datetime.now(timezone.utc)
        deck = DeckRow(
            id=deck_id,
            owner_id=owner_id,
            name=name,
            deck_type=deck_type,
            theme=theme,
            aspect_ratio=aspect_ratio,
            generation_payload=generation_payload,
            current_version_id=None,
            created_at=now,
            updated_at=now,
        )
        version = DeckVersionRow(
            id=version_id,
            deck_id=deck_id,
            version_number=1,
            storage_key=storage_key,
            sha256=sha256,
            size_bytes=size_bytes,
            source="generated",
            created_by=owner_id,
            created_at=now,
        )
        async with self._database.session() as session:
            async with session.begin():
                session.add(deck)
                await session.flush()
                session.add(version)
                await session.flush()
                deck.current_version_id = version_id
                deck.updated_at = now
                await session.flush()
                await session.refresh(deck)
                record = _deck_record(deck, version)
        return record

    async def get(self, deck_id: str, owner_id: str) -> DeckRecord | None:
        async with self._database.session() as session:
            deck = await session.scalar(
                select(DeckRow).where(DeckRow.id == deck_id, DeckRow.owner_id == owner_id)
            )
            if deck is None:
                return None
            version = None
            if deck.current_version_id is not None:
                version = await session.scalar(
                    select(DeckVersionRow).where(
                        DeckVersionRow.id == deck.current_version_id,
                        DeckVersionRow.deck_id == deck.id,
                    )
                )
            return _deck_record(deck, version)

    async def list_all(
        self,
        owner_id: str,
        search: str = "",
        deck_type: str = "",
        sort: str = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> list[DeckSummaryRecord]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if sort not in {"newest", "oldest", "name"}:
            raise ValueError("sort must be newest, oldest, or name")

        statement = (
            select(DeckRow, DeckVersionRow.version_number)
            .outerjoin(
                DeckVersionRow,
                and_(
                    DeckVersionRow.id == DeckRow.current_version_id,
                    DeckVersionRow.deck_id == DeckRow.id,
                ),
            )
            .where(DeckRow.owner_id == owner_id)
        )
        if search:
            statement = statement.where(func.lower(DeckRow.name).contains(search.lower()))
        if deck_type:
            statement = statement.where(DeckRow.deck_type == deck_type)
        if sort == "oldest":
            statement = statement.order_by(DeckRow.created_at.asc(), DeckRow.id.asc())
        elif sort == "name":
            statement = statement.order_by(func.lower(DeckRow.name).asc(), DeckRow.id.asc())
        else:
            statement = statement.order_by(DeckRow.created_at.desc(), DeckRow.id.asc())
        statement = statement.limit(limit).offset(offset)

        async with self._database.session() as session:
            rows = (await session.execute(statement)).all()

        # The 100-row cap bounds JSON loading while slide_count remains portable
        # across SQLite and PostgreSQL JSON implementations.
        summaries = []
        for deck, current_version_number in rows:
            payload = deck.generation_payload
            slides = payload.get("slides") if isinstance(payload, dict) else None
            summaries.append(
                DeckSummaryRecord(
                    id=deck.id,
                    name=deck.name,
                    deck_type=deck.deck_type,
                    slide_count=len(slides) if isinstance(slides, list) else 0,
                    current_version_id=deck.current_version_id,
                    current_version_number=current_version_number,
                    created_at=_utc(deck.created_at),
                    updated_at=_utc(deck.updated_at),
                )
            )
        return summaries

    async def rename(self, deck_id: str, owner_id: str, name: str) -> bool:
        async with self._database.session() as session:
            async with session.begin():
                result = await session.execute(
                    update(DeckRow)
                    .where(DeckRow.id == deck_id, DeckRow.owner_id == owner_id)
                    .values(name=name, updated_at=datetime.now(timezone.utc))
                )
            return bool(result.rowcount)

    async def delete(self, deck_id: str, owner_id: str) -> list[str]:
        async with self._database.session() as session:
            async with _serialized_write(session):
                deck = await session.scalar(
                    _owned_deck_for_write(
                        deck_id,
                        owner_id,
                        session.bind.dialect.name if session.bind is not None else "",
                    )
                )
                if deck is None:
                    return []
                keys = list(
                    await session.scalars(
                        select(DeckVersionRow.storage_key).where(DeckVersionRow.deck_id == deck_id)
                    )
                )
                deck.current_version_id = None
                await session.flush()
                await session.execute(sqlalchemy_delete(DeckRow).where(DeckRow.id == deck_id))
                return keys

    async def list_versions(self, deck_id: str, owner_id: str) -> list[DeckVersionRecord]:
        async with self._database.session() as session:
            rows = await session.scalars(
                select(DeckVersionRow)
                .join(DeckRow, DeckRow.id == DeckVersionRow.deck_id)
                .where(DeckVersionRow.deck_id == deck_id, DeckRow.owner_id == owner_id)
                .order_by(DeckVersionRow.version_number.desc())
            )
            return [_version_record(row) for row in rows]

    async def append_version(
        self,
        *,
        deck_id: str,
        owner_id: str,
        version_id: str,
        storage_key: str,
        sha256: str,
        size_bytes: int,
        source: str,
        created_by: str,
        base_version_id: str | None = None,
        generation_payload: dict | None = None,
    ) -> DeckVersionRecord:
        now = datetime.now(timezone.utc)
        async with self._database.session() as session:
            async with _serialized_write(session):
                deck = await session.scalar(
                    _owned_deck_for_write(
                        deck_id,
                        owner_id,
                        session.bind.dialect.name if session.bind is not None else "",
                    )
                )
                if deck is None:
                    raise LookupError("Deck not found")
                if base_version_id is not None and base_version_id != deck.current_version_id:
                    logger.warning(
                        "deck_version_stale_base",
                        deck_id=deck_id,
                        owner_id=owner_id,
                        base_version_id=base_version_id,
                        current_version_id=deck.current_version_id,
                        new_version_id=version_id,
                    )
                maximum = await session.scalar(
                    select(func.max(DeckVersionRow.version_number)).where(
                        DeckVersionRow.deck_id == deck_id
                    )
                )
                version = DeckVersionRow(
                    id=version_id,
                    deck_id=deck_id,
                    version_number=(maximum or 0) + 1,
                    storage_key=storage_key,
                    sha256=sha256,
                    size_bytes=size_bytes,
                    source=source,
                    created_by=created_by,
                    created_at=now,
                )
                session.add(version)
                await session.flush()
                deck.current_version_id = version_id
                deck.updated_at = now
                if generation_payload is not None:
                    deck.generation_payload = generation_payload
            return _version_record(version)

    async def version(
        self,
        deck_id: str,
        version_id: str,
        owner_id: str,
    ) -> DeckVersionRecord | None:
        async with self._database.session() as session:
            row = await session.scalar(
                select(DeckVersionRow)
                .join(DeckRow, DeckRow.id == DeckVersionRow.deck_id)
                .where(
                    DeckVersionRow.id == version_id,
                    DeckVersionRow.deck_id == deck_id,
                    DeckRow.owner_id == owner_id,
                )
            )
            return _version_record(row) if row is not None else None

    async def stale_versions(self, deck_id: str, keep: int) -> list[DeckVersionRecord]:
        if keep < 1:
            raise ValueError("keep must be at least 1")
        async with self._database.session() as session:
            deck = await session.get(DeckRow, deck_id)
            if deck is None:
                return []
            rows = list(
                await session.scalars(
                    select(DeckVersionRow)
                    .where(DeckVersionRow.deck_id == deck_id)
                    .order_by(DeckVersionRow.version_number.desc())
                )
            )
            return [
                _version_record(row)
                for row in rows[keep:]
                if row.id != deck.current_version_id
            ]

    async def delete_version_rows(self, version_ids: list[str]) -> None:
        if not version_ids:
            return
        async with self._database.session() as session:
            async with _serialized_write(session):
                current_ids = set(
                    await session.scalars(
                        select(DeckRow.current_version_id).where(
                            DeckRow.current_version_id.in_(version_ids)
                        )
                    )
                )
                deletable_ids = set(version_ids) - current_ids
                if deletable_ids:
                    await session.execute(
                        sqlalchemy_delete(DeckVersionRow).where(
                            DeckVersionRow.id.in_(deletable_ids)
                        )
                    )

    async def all_storage_keys(self) -> set[str]:
        async with self._database.session() as session:
            return set(await session.scalars(select(DeckVersionRow.storage_key)))

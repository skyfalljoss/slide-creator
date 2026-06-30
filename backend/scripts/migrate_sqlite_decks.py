"""Import legacy slide-JSON decks into immutable versioned PPTX storage."""

import argparse
import asyncio
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

from app.config import settings
from app.models.schemas import SlideData
from app.services.platform.database import Database
from app.services.platform.deck_files import (
    DeckFileStorage,
    GCSDeckFileStorage,
    LocalDeckFileStorage,
)
from app.services.platform.deck_repository import (
    DeckRepository,
    DeckWriteRolledBackError,
)
from app.services.presentation.pptx_engine import PptxEngine
from app.services.presentation.pptx_validation import validate_pptx


class MigrationRepository(Protocol):
    async def contains_deck_id(self, deck_id: str) -> bool: ...
    async def import_with_initial_version(self, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class MigrationFailure:
    deck_id: str
    reason: str


@dataclass(frozen=True)
class MigrationResult:
    migrated: int
    skipped: int
    failed: int
    failures: tuple[MigrationFailure, ...] = ()


def _parse_json(value: object, *, field: str) -> object:
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field} is not valid JSON") from exc
    return value


def _parse_timestamp(value: object, *, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} is not a valid timestamp") from exc
    else:
        raise ValueError(f"{field} is missing")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _text(row: sqlite3.Row, field: str, default: str, maximum: int) -> str:
    value = row[field] if field in row.keys() else default
    if value is None:
        value = default
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    value = value.strip()
    if not value:
        value = default
    if len(value) > maximum:
        raise ValueError(f"{field} exceeds {maximum} characters")
    return value


def _legacy_slides_and_payload(row: sqlite3.Row) -> tuple[list[SlideData], dict]:
    raw_payload = row["generation_payload"] if "generation_payload" in row.keys() else None
    payload = _parse_json(raw_payload, field="generation_payload")
    if payload is None:
        payload_dict: dict[str, object] = {}
    elif isinstance(payload, dict):
        payload_dict = payload
    elif isinstance(payload, list):
        payload_dict = {"slides": payload}
    else:
        raise ValueError("generation_payload must be a JSON object or slide list")

    raw_slides = row["slides"] if "slides" in row.keys() else payload_dict.get("slides")
    parsed_slides = _parse_json(raw_slides, field="slides")
    if not isinstance(parsed_slides, list) or not parsed_slides:
        raise ValueError("slides must be a non-empty JSON list")
    slides: list[SlideData] = []
    for index, item in enumerate(parsed_slides, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"slide {index} must be a JSON object")
        try:
            normalized = dict(item)
            for nested_field in ("content", "enrichment", "assets"):
                nested = normalized.get(nested_field)
                if isinstance(nested, dict):
                    for key, value in nested.items():
                        normalized.setdefault(key, value)
            slides.append(SlideData.model_validate(normalized))
        except ValueError as exc:
            raise ValueError(f"slide {index} is invalid") from exc
    if not payload_dict:
        payload_dict = {"slides": parsed_slides}
    return slides, payload_dict


def _read_legacy_rows(sqlite_path: Path) -> list[sqlite3.Row]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"Legacy SQLite database not found: {sqlite_path}")
    uri = sqlite_path.resolve().as_uri().replace("file://", "file:", 1) + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
            ("table", "decks"),
        ).fetchone()
        if table is None:
            raise ValueError("Legacy SQLite database has no decks table")
        columns = {
            row[1] for row in connection.execute('PRAGMA table_info("decks")').fetchall()
        }
        missing = {"id", "slides", "created_at", "updated_at"} - columns
        if missing:
            raise ValueError(
                "Legacy decks table is missing required columns: "
                + ", ".join(sorted(missing))
            )
        return connection.execute('SELECT * FROM "decks" ORDER BY "id"').fetchall()
    finally:
        connection.close()


async def migrate_sqlite_decks(
    sqlite_path: Path | str,
    owner_id: str,
    repository: MigrationRepository,
    storage: DeckFileStorage,
    *,
    template_path: str | None,
    max_file_bytes: int = 50_000_000,
) -> MigrationResult:
    if not owner_id.strip():
        raise ValueError("owner_id must not be empty")
    rows = await asyncio.to_thread(_read_legacy_rows, Path(sqlite_path))
    migrated = skipped = 0
    failures: list[MigrationFailure] = []
    for row in rows:
        deck_id = str(row["id"] or "").strip()
        uploaded = False
        storage_key = ""
        try:
            if not deck_id or len(deck_id) > 36:
                raise ValueError("id must contain at most 36 characters")
            if await repository.contains_deck_id(deck_id):
                skipped += 1
                continue
            slides, payload = _legacy_slides_and_payload(row)
            name = _text(row, "name", "Untitled Deck", 500)
            deck_type = _text(row, "deck_type", "unknown", 64)
            theme = _text(row, "theme", "minimalist", 64)
            aspect_ratio = _text(row, "aspect_ratio", "16:9", 16)
            created_at = _parse_timestamp(row["created_at"], field="created_at")
            updated_at = _parse_timestamp(row["updated_at"], field="updated_at")
            content = await asyncio.to_thread(
                PptxEngine(
                    template_path=template_path,
                    theme=theme,
                    aspect_ratio=aspect_ratio,
                ).render,
                slides,
            )
            await asyncio.to_thread(validate_pptx, content, max_file_bytes)
            checksum = await asyncio.to_thread(lambda: hashlib.sha256(content).hexdigest())
            version_id = str(uuid5(NAMESPACE_URL, f"slideforge:migration:{deck_id}"))
            storage_key = f"decks/{deck_id}/versions/{version_id}.pptx"
            try:
                await storage.put(storage_key, content)
                uploaded = True
            except FileExistsError:
                existing = await storage.read(storage_key)
                if hashlib.sha256(existing).hexdigest() != checksum:
                    raise ValueError("existing migration object has a different checksum")
            await repository.import_with_initial_version(
                deck_id=deck_id,
                version_id=version_id,
                owner_id=owner_id,
                name=name,
                deck_type=deck_type,
                theme=theme,
                aspect_ratio=aspect_ratio,
                generation_payload=payload,
                storage_key=storage_key,
                sha256=checksum,
                size_bytes=len(content),
                created_at=created_at,
                updated_at=updated_at,
            )
            migrated += 1
        except asyncio.CancelledError:
            raise
        except DeckWriteRolledBackError as exc:
            if uploaded:
                try:
                    committed = await repository.contains_deck_id(deck_id)
                except Exception:
                    committed = True
                if not committed:
                    await storage.delete(storage_key)
            failures.append(MigrationFailure(deck_id or "<missing>", type(exc.cause).__name__))
        except Exception as exc:
            # Unknown repository failures can represent an uncertain commit. Keep
            # immutable data for reconciliation rather than risking data loss.
            reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            failures.append(MigrationFailure(deck_id or "<missing>", reason))
    return MigrationResult(migrated, skipped, len(failures), tuple(failures))


def _storage() -> DeckFileStorage:
    if settings.storage_provider == "gcs":
        return GCSDeckFileStorage(settings.gcs_bucket)
    return LocalDeckFileStorage(Path(settings.local_deck_file_dir))


async def _main(args: argparse.Namespace) -> int:
    database = Database(settings.database_url)
    storage = _storage()
    try:
        result = await migrate_sqlite_decks(
            args.sqlite_path,
            args.owner_id,
            DeckRepository(database),
            storage,
            template_path=settings.sample_template_path,
            max_file_bytes=settings.onlyoffice_max_file_bytes,
        )
    finally:
        await database.dispose()
        close = getattr(storage, "close", None)
        if close is not None:
            await close()
    for failure in result.failures:
        print(f"failed deck {failure.deck_id}: {failure.reason}")
    print(
        f"migrated={result.migrated} skipped={result.skipped} failed={result.failed}"
    )
    return 1 if result.failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", type=Path, required=True)
    parser.add_argument("--owner-id", required=True)
    return asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

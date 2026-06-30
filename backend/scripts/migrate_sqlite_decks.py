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
    DeckRecord,
    DeckRepository,
    DeckWriteRolledBackError,
)
from app.services.presentation.pptx_engine import PptxEngine
from app.services.presentation.pptx_validation import validate_pptx


class MigrationRepository(Protocol):
    async def get_global(self, deck_id: str) -> DeckRecord | None: ...
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


@dataclass(frozen=True)
class MigrationLimits:
    max_sqlite_bytes: int = 1_000_000_000
    max_row_json_bytes: int = 20_000_000
    max_json_depth: int = 20
    max_slides: int = 200
    max_total_text_chars: int = 2_000_000
    max_text_chars: int = 200_000
    max_list_items: int = 20_000
    max_image_bytes: int = 50_000_000
    fetch_batch_size: int = 100

    def __post_init__(self) -> None:
        if any(value <= 0 for value in self.__dict__.values()):
            raise ValueError("migration limits must be positive")


def _raw_json_depth(value: str, *, field: str, maximum: int) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in value:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > maximum:
                raise ValueError(f"{field} exceeds maximum JSON depth")
        elif character in "]}":
            depth -= 1


def _validate_decoded_budget(value: object, limits: MigrationLimits) -> None:
    text_chars = 0
    list_items = 0
    image_bytes = 0

    def visit(item: object, depth: int, field: str = "") -> None:
        nonlocal text_chars, list_items, image_bytes
        if depth > limits.max_json_depth:
            raise ValueError("decoded JSON exceeds maximum depth")
        if isinstance(item, dict):
            for key, nested in item.items():
                visit(nested, depth + 1, str(key))
        elif isinstance(item, list):
            list_items += len(item)
            if list_items > limits.max_list_items:
                raise ValueError("decoded JSON contains too many list items")
            for nested in item:
                visit(nested, depth + 1, field)
        elif isinstance(item, str):
            if len(item) > limits.max_text_chars:
                raise ValueError("a text field exceeds the character limit")
            text_chars += len(item)
            if text_chars > limits.max_total_text_chars:
                raise ValueError("deck text exceeds the total character limit")
            if field == "image_b64":
                image_bytes += (len(item) * 3) // 4
                if image_bytes > limits.max_image_bytes:
                    raise ValueError("embedded images exceed the decoded size limit")

    visit(value, 0)


def _parse_json(
    value: object,
    *,
    field: str,
    limits: MigrationLimits,
) -> object:
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        if len(raw) > limits.max_row_json_bytes:
            raise ValueError(f"{field} exceeds the JSON byte limit")
        value = raw.decode("utf-8")
    if isinstance(value, str):
        encoded_size = len(value.encode("utf-8"))
        if encoded_size > limits.max_row_json_bytes:
            raise ValueError(f"{field} exceeds the JSON byte limit")
        _raw_json_depth(value, field=field, maximum=limits.max_json_depth)
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field} is not valid JSON") from exc
    else:
        decoded = value
    _validate_decoded_budget(decoded, limits)
    return decoded


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


def _legacy_slides_and_payload(
    row: sqlite3.Row, limits: MigrationLimits
) -> tuple[list[SlideData], dict]:
    raw_payload = row["generation_payload"] if "generation_payload" in row.keys() else None
    payload = _parse_json(raw_payload, field="generation_payload", limits=limits)
    if payload is None:
        payload_dict: dict[str, object] = {}
    elif isinstance(payload, dict):
        payload_dict = payload
    elif isinstance(payload, list):
        payload_dict = {"slides": payload}
    else:
        raise ValueError("generation_payload must be a JSON object or slide list")

    raw_slides = row["slides"] if "slides" in row.keys() else payload_dict.get("slides")
    parsed_slides = _parse_json(raw_slides, field="slides", limits=limits)
    if not isinstance(parsed_slides, list) or not parsed_slides:
        raise ValueError("slides must be a non-empty JSON list")
    if len(parsed_slides) > limits.max_slides:
        raise ValueError(f"slides exceeds the {limits.max_slides}-slide limit")
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


class _LegacyDeckReader:
    def __init__(self, connection: sqlite3.Connection, cursor: sqlite3.Cursor) -> None:
        self._connection = connection
        self._cursor = cursor

    def fetchmany(self, size: int) -> list[sqlite3.Row]:
        return self._cursor.fetchmany(size)

    def close(self) -> None:
        self._cursor.close()
        self._connection.close()


def _open_legacy_reader(
    sqlite_path: Path, *, max_sqlite_bytes: int
) -> _LegacyDeckReader:
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"Legacy SQLite database not found: {sqlite_path}")
    if sqlite_path.stat().st_size > max_sqlite_bytes:
        raise ValueError("Legacy SQLite database exceeds the file size limit")
    uri = sqlite_path.resolve().as_uri().replace("file://", "file:", 1) + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
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
        cursor = connection.execute('SELECT * FROM "decks" ORDER BY "id"')
        return _LegacyDeckReader(connection, cursor)
    except BaseException:
        connection.close()
        raise


def _same_time(left: datetime, right: datetime) -> bool:
    return left.astimezone(timezone.utc) == right.astimezone(timezone.utc)


async def _matching_existing(
    existing: DeckRecord | None,
    *,
    owner_id: str,
    name: str,
    deck_type: str,
    theme: str,
    aspect_ratio: str,
    payload: dict,
    version_id: str,
    storage_key: str,
    checksum: str,
    size_bytes: int,
    created_at: datetime,
    updated_at: datetime,
    storage: DeckFileStorage,
) -> bool:
    if existing is None or existing.current_version is None:
        return False
    version = existing.current_version
    metadata_matches = (
        existing.owner_id == owner_id
        and existing.name == name
        and existing.deck_type == deck_type
        and existing.theme == theme
        and existing.aspect_ratio == aspect_ratio
        and existing.generation_payload == payload
        and _same_time(existing.created_at, created_at)
        and _same_time(existing.updated_at, updated_at)
        and existing.current_version_id == version_id
        and version.id == version_id
        and version.version_number == 1
        and version.storage_key == storage_key
        and version.sha256 == checksum
        and version.size_bytes == size_bytes
        and version.source == "migration"
        and version.created_by == owner_id
        and _same_time(version.created_at, created_at)
    )
    if not metadata_matches:
        return False
    try:
        content = await storage.read(storage_key)
    except Exception:
        return False
    return len(content) == size_bytes and hashlib.sha256(content).hexdigest() == checksum


async def migrate_sqlite_decks(
    sqlite_path: Path | str,
    owner_id: str,
    repository: MigrationRepository,
    storage: DeckFileStorage,
    *,
    template_path: str | None,
    max_file_bytes: int = 50_000_000,
    limits: MigrationLimits | None = None,
) -> MigrationResult:
    if not owner_id.strip():
        raise ValueError("owner_id must not be empty")
    limits = limits or MigrationLimits()
    reader = await asyncio.to_thread(
        _open_legacy_reader,
        Path(sqlite_path),
        max_sqlite_bytes=limits.max_sqlite_bytes,
    )
    migrated = skipped = 0
    failures: list[MigrationFailure] = []
    try:
        while rows := await asyncio.to_thread(
            reader.fetchmany, limits.fetch_batch_size
        ):
            for row in rows:
                deck_id = str(row["id"] or "").strip()
                uploaded = False
                storage_key = ""
                identity: dict[str, Any] | None = None
                try:
                    if not deck_id or len(deck_id) > 36:
                        raise ValueError("id must contain at most 36 characters")
                    existing_deck = await repository.get_global(deck_id)
                    if existing_deck is not None and existing_deck.owner_id != owner_id:
                        raise ValueError("deck ID already belongs to another owner")
                    raw_json_bytes = sum(
                        len(value.encode("utf-8"))
                        if isinstance(value, str)
                        else len(value)
                        for field in ("slides", "generation_payload")
                        if field in row.keys()
                        and isinstance((value := row[field]), (str, bytes, bytearray))
                    )
                    if raw_json_bytes > limits.max_row_json_bytes:
                        raise ValueError("row exceeds the JSON byte limit")
                    slides, payload = _legacy_slides_and_payload(row, limits)
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
                    checksum = await asyncio.to_thread(
                        lambda: hashlib.sha256(content).hexdigest()
                    )
                    version_id = str(
                        uuid5(NAMESPACE_URL, f"slideforge:migration:{deck_id}")
                    )
                    storage_key = f"decks/{deck_id}/versions/{version_id}.pptx"
                    identity = {
                        "owner_id": owner_id,
                        "name": name,
                        "deck_type": deck_type,
                        "theme": theme,
                        "aspect_ratio": aspect_ratio,
                        "payload": payload,
                        "version_id": version_id,
                        "storage_key": storage_key,
                        "checksum": checksum,
                        "size_bytes": len(content),
                        "created_at": created_at,
                        "updated_at": updated_at,
                    }
                    if existing_deck is not None:
                        if await _matching_existing(
                            existing_deck, storage=storage, **identity
                        ):
                            skipped += 1
                            continue
                        raise ValueError(
                            "existing same-owner deck does not match authoritative version 1"
                        )
                    try:
                        await storage.put(storage_key, content)
                        uploaded = True
                    except FileExistsError:
                        stored_content = await storage.read(storage_key)
                        if hashlib.sha256(stored_content).hexdigest() != checksum:
                            raise ValueError(
                                "existing migration object has a different checksum"
                            )
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
                    reason = type(exc.cause).__name__
                    reconciliation_safe = True
                    try:
                        winner = await repository.get_global(deck_id)
                        winner_matches = identity is not None and await _matching_existing(
                            winner, storage=storage, **identity
                        )
                    except Exception as reconciliation_error:
                        winner = None
                        winner_matches = False
                        reconciliation_safe = False
                        reason += (
                            "; reconciliation failed "
                            f"({type(reconciliation_error).__name__})"
                        )
                    if winner_matches:
                        skipped += 1
                        continue
                    winner_key = (
                        winner.current_version.storage_key
                        if winner is not None and winner.current_version is not None
                        else None
                    )
                    if uploaded and reconciliation_safe and winner_key != storage_key:
                        try:
                            await storage.delete(storage_key)
                        except Exception as compensation_error:
                            reason += (
                                "; compensation delete failed "
                                f"({type(compensation_error).__name__})"
                            )
                    failures.append(MigrationFailure(deck_id or "<missing>", reason))
                except Exception as exc:
                    # Unknown repository failures can represent an uncertain commit.
                    # Preserve immutable data for later reconciliation.
                    reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                    failures.append(MigrationFailure(deck_id or "<missing>", reason))
    finally:
        await asyncio.to_thread(reader.close)
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
            limits=MigrationLimits(
                max_sqlite_bytes=args.max_sqlite_bytes,
                max_row_json_bytes=args.max_row_json_bytes,
                max_json_depth=args.max_json_depth,
                max_slides=args.max_slides,
                max_total_text_chars=args.max_total_text_chars,
                max_text_chars=args.max_text_chars,
                max_list_items=args.max_list_items,
                max_image_bytes=args.max_image_bytes,
                fetch_batch_size=args.fetch_batch_size,
            ),
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
    parser.add_argument("--max-sqlite-bytes", type=int, default=1_000_000_000)
    parser.add_argument("--max-row-json-bytes", type=int, default=20_000_000)
    parser.add_argument("--max-json-depth", type=int, default=20)
    parser.add_argument("--max-slides", type=int, default=200)
    parser.add_argument("--max-total-text-chars", type=int, default=2_000_000)
    parser.add_argument("--max-text-chars", type=int, default=200_000)
    parser.add_argument("--max-list-items", type=int, default=20_000)
    parser.add_argument("--max-image-bytes", type=int, default=50_000_000)
    parser.add_argument("--fetch-batch-size", type=int, default=100)
    return asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

import asyncio
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Awaitable, BinaryIO, Protocol, TypeVar

from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage as gcs

from app.config import settings

PPTX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
DECK_STREAM_CHUNK_SIZE = 256 * 1024
_MAX_STREAM_CHUNK_SIZE = 1024 * 1024
_T = TypeVar("_T")


async def await_destructive(operation: Awaitable[_T]) -> _T:
    """Finish an irreversible operation before propagating caller cancellation."""
    task = asyncio.ensure_future(operation)
    cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as exc:
            cancellation = exc
        except Exception:
            break
    try:
        result = task.result()
    except Exception as exc:
        if cancellation is not None:
            raise cancellation from exc
        raise
    if cancellation is not None:
        raise cancellation
    return result


class DeckFileStream(Protocol):
    @property
    def closed(self) -> bool: ...
    def __aiter__(self) -> "DeckFileStream": ...
    async def __anext__(self) -> bytes: ...
    async def aclose(self) -> None: ...


class DeckFileStorage(Protocol):
    async def put(self, key: str, content: bytes) -> None: ...
    async def read(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def list_keys(self, prefix: str) -> list[str]: ...
    async def list_objects(self, prefix: str) -> list["DeckFileObject"]: ...
    async def open_stream(
        self, key: str, chunk_size: int = DECK_STREAM_CHUNK_SIZE
    ) -> DeckFileStream: ...


@dataclass(frozen=True)
class DeckFileObject:
    key: str
    updated_at: datetime | None


class _ThreadedDeckFileStream:
    def __init__(
        self,
        handle: BinaryIO,
        *,
        first_chunk: bytes,
        chunk_size: int,
        key: str,
        not_found_exceptions: tuple[type[BaseException], ...],
    ) -> None:
        self._handle = handle
        self._first_chunk: bytes | None = first_chunk
        self._chunk_size = chunk_size
        self._key = key
        self._not_found_exceptions = not_found_exceptions
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def __aiter__(self) -> "_ThreadedDeckFileStream":
        return self

    async def __anext__(self) -> bytes:
        if self._closed:
            raise StopAsyncIteration
        if self._first_chunk is not None:
            chunk = self._first_chunk
            self._first_chunk = None
        else:
            try:
                chunk = await asyncio.to_thread(self._handle.read, self._chunk_size)
            except self._not_found_exceptions as exc:
                await self.aclose()
                raise FileNotFoundError(self._key) from exc
            except BaseException:
                await self.aclose()
                raise
        if chunk:
            return chunk
        await self.aclose()
        raise StopAsyncIteration

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await asyncio.to_thread(self._handle.close)


def _validate_chunk_size(chunk_size: int) -> None:
    if not 1 <= chunk_size <= _MAX_STREAM_CHUNK_SIZE:
        raise ValueError("chunk_size must be between 1 byte and 1 MiB")


async def _open_prefetched_stream(
    *,
    handle: BinaryIO,
    key: str,
    chunk_size: int,
    not_found_exceptions: tuple[type[BaseException], ...] = (),
) -> DeckFileStream:
    try:
        first_chunk = await asyncio.to_thread(handle.read, chunk_size)
    except not_found_exceptions as exc:
        await asyncio.to_thread(handle.close)
        raise FileNotFoundError(key) from exc
    except BaseException:
        await asyncio.to_thread(handle.close)
        raise
    return _ThreadedDeckFileStream(
        handle,
        first_chunk=first_chunk,
        chunk_size=chunk_size,
        key=key,
        not_found_exceptions=not_found_exceptions,
    )


def _normalize_key(key: str) -> str:
    if (
        not isinstance(key, str)
        or not key
        or key.endswith("/")
        or "\\" in key
        or "\x00" in key
    ):
        raise ValueError("Invalid storage key")
    if key == ".":
        raise ValueError("Invalid storage key")
    path = PurePosixPath(key)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in key.split("/")):
        raise ValueError("Invalid storage key")
    return path.as_posix()


def _normalize_prefix(prefix: str) -> str:
    if prefix == "":
        return ""
    has_separator = prefix.endswith("/")
    candidate = prefix[:-1] if has_separator else prefix
    normalized = _normalize_key(candidate)
    return f"{normalized}/" if has_separator else normalized


class LocalDeckFileStorage:
    """Immutable storage below a trusted local root.

    The root and its parent filesystem are an administrative trust boundary.
    Symlink checks prevent ordinary escapes, but can still race with hostile,
    concurrent filesystem mutation because portable Python lacks openat-style
    path traversal controls.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self._resolved_root: Path | None = None
        self._root_lock = threading.Lock()

    def _trusted_root(self) -> Path:
        with self._root_lock:
            if self._resolved_root is None:
                self._resolved_root = self.root.resolve()
            return self._resolved_root

    def _path_for(self, key: str) -> Path:
        normalized = _normalize_key(key)
        root = self._trusted_root()
        path = root.joinpath(*PurePosixPath(normalized).parts)
        current = root
        for part in PurePosixPath(normalized).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Invalid storage key")
        try:
            path.resolve(strict=False).relative_to(root)
        except ValueError as exc:
            raise ValueError("Invalid storage key") from exc
        return path

    async def put(self, key: str, content: bytes) -> None:
        normalized = _normalize_key(key)

        def write() -> None:
            path = self._path_for(normalized)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._path_for(normalized)
            with path.open("xb") as output:
                output.write(content)

        await asyncio.to_thread(write)

    async def read(self, key: str) -> bytes:
        normalized = _normalize_key(key)

        def read_bytes() -> bytes:
            return self._path_for(normalized).read_bytes()

        return await asyncio.to_thread(read_bytes)

    async def open_stream(
        self, key: str, chunk_size: int = DECK_STREAM_CHUNK_SIZE
    ) -> DeckFileStream:
        normalized = _normalize_key(key)
        _validate_chunk_size(chunk_size)

        def open_file() -> BinaryIO:
            return self._path_for(normalized).open("rb")

        handle = await asyncio.to_thread(open_file)
        return await _open_prefetched_stream(
            handle=handle,
            key=normalized,
            chunk_size=chunk_size,
        )

    async def delete(self, key: str) -> None:
        normalized = _normalize_key(key)

        def unlink() -> None:
            try:
                self._path_for(normalized).unlink()
            except FileNotFoundError:
                pass

        await asyncio.to_thread(unlink)

    async def exists(self, key: str) -> bool:
        normalized = _normalize_key(key)

        def is_file() -> bool:
            return self._path_for(normalized).is_file()

        return await asyncio.to_thread(is_file)

    async def list_keys(self, prefix: str) -> list[str]:
        return [item.key for item in await self.list_objects(prefix)]

    async def list_objects(self, prefix: str) -> list[DeckFileObject]:
        normalized_prefix = _normalize_prefix(prefix)

        def list_files() -> list[DeckFileObject]:
            root = self._trusted_root()
            if not root.exists():
                return []
            objects: list[DeckFileObject] = []
            for directory, directory_names, file_names in os.walk(root, followlinks=False):
                directory_path = Path(directory)
                directory_names[:] = [
                    name for name in directory_names if not (directory_path / name).is_symlink()
                ]
                for name in file_names:
                    path = directory_path / name
                    if path.is_symlink() or not path.is_file():
                        continue
                    try:
                        relative = path.resolve(strict=True).relative_to(root).as_posix()
                    except (FileNotFoundError, ValueError):
                        continue
                    if relative.startswith(normalized_prefix):
                        try:
                            modified = datetime.fromtimestamp(
                                path.stat().st_mtime, tz=timezone.utc
                            )
                        except OSError:
                            modified = None
                        objects.append(DeckFileObject(relative, modified))
            return sorted(objects, key=lambda item: item.key)

        return await asyncio.to_thread(list_files)


class GCSDeckFileStorage:
    def __init__(self, bucket_name: str | None = None, client: gcs.Client | None = None):
        self.bucket_name = bucket_name or settings.gcs_bucket
        self._owns_client = client is None
        self._client = client or gcs.Client(project=settings.gcp_project_id)

    async def close(self) -> None:
        if self._owns_client:
            await asyncio.to_thread(self._client.close)

    def _bucket(self) -> gcs.Bucket:
        return self._client.bucket(self.bucket_name)

    async def put(self, key: str, content: bytes) -> None:
        normalized = _normalize_key(key)
        blob = self._bucket().blob(normalized)
        try:
            await asyncio.to_thread(
                blob.upload_from_string,
                content,
                content_type=PPTX_CONTENT_TYPE,
                if_generation_match=0,
            )
        except PreconditionFailed as exc:
            raise FileExistsError(normalized) from exc

    async def read(self, key: str) -> bytes:
        blob = self._bucket().blob(_normalize_key(key))
        try:
            return await asyncio.to_thread(blob.download_as_bytes)
        except NotFound as exc:
            raise FileNotFoundError(key) from exc

    async def open_stream(
        self, key: str, chunk_size: int = DECK_STREAM_CHUNK_SIZE
    ) -> DeckFileStream:
        normalized = _normalize_key(key)
        _validate_chunk_size(chunk_size)
        blob = self._bucket().blob(normalized)
        try:
            handle = await asyncio.to_thread(blob.open, "rb", chunk_size=chunk_size)
        except NotFound as exc:
            raise FileNotFoundError(normalized) from exc
        return await _open_prefetched_stream(
            handle=handle,
            key=normalized,
            chunk_size=chunk_size,
            not_found_exceptions=(NotFound,),
        )

    async def delete(self, key: str) -> None:
        blob = self._bucket().blob(_normalize_key(key))
        try:
            await asyncio.to_thread(blob.delete)
        except NotFound:
            pass

    async def exists(self, key: str) -> bool:
        blob = self._bucket().blob(_normalize_key(key))
        return await asyncio.to_thread(blob.exists)

    async def list_keys(self, prefix: str) -> list[str]:
        return [item.key for item in await self.list_objects(prefix)]

    async def list_objects(self, prefix: str) -> list[DeckFileObject]:
        normalized = _normalize_prefix(prefix)

        def list_blob_names() -> list[DeckFileObject]:
            blobs = self._bucket().list_blobs(prefix=normalized)
            return sorted(
                (DeckFileObject(blob.name, getattr(blob, "updated", None)) for blob in blobs),
                key=lambda item: item.key,
            )

        return await asyncio.to_thread(list_blob_names)

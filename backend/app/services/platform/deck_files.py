import asyncio
import os
import threading
from pathlib import Path, PurePosixPath
from typing import Protocol

from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage as gcs

from app.config import settings

PPTX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class DeckFileStorage(Protocol):
    async def put(self, key: str, content: bytes) -> None: ...
    async def read(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def list_keys(self, prefix: str) -> list[str]: ...


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
        normalized_prefix = _normalize_prefix(prefix)

        def list_files() -> list[str]:
            root = self._trusted_root()
            if not root.exists():
                return []
            keys: list[str] = []
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
                        keys.append(relative)
            return sorted(keys)

        return await asyncio.to_thread(list_files)


class GCSDeckFileStorage:
    def __init__(self, bucket_name: str | None = None, client: gcs.Client | None = None):
        self.bucket_name = bucket_name or settings.gcs_bucket
        self._client = client or gcs.Client(project=settings.gcp_project_id)

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
        normalized = _normalize_prefix(prefix)

        def list_blob_names() -> list[str]:
            blobs = self._bucket().list_blobs(prefix=normalized)
            return sorted(blob.name for blob in blobs)

        return await asyncio.to_thread(list_blob_names)

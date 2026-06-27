from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from google.api_core.exceptions import NotFound, PreconditionFailed
import pytest

from app.config import settings
from app.services.platform.deck_files import GCSDeckFileStorage, LocalDeckFileStorage


@pytest.mark.asyncio
async def test_local_storage_round_trip_and_missing_delete(tmp_path: Path):
    storage = LocalDeckFileStorage(tmp_path)
    key = "decks/d1/versions/v1.pptx"

    await storage.put(key, b"pptx")

    assert await storage.exists(key) is True
    assert await storage.read(key) == b"pptx"
    assert await storage.list_keys("decks/") == [key]
    await storage.delete(key)
    await storage.delete(key)
    assert await storage.exists(key) is False


@pytest.mark.asyncio
async def test_local_storage_rejects_overwrite(tmp_path: Path):
    storage = LocalDeckFileStorage(tmp_path)
    key = "decks/d1/versions/v1.pptx"
    await storage.put(key, b"first")

    with pytest.raises(FileExistsError):
        await storage.put(key, b"second")

    assert await storage.read(key) == b"first"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key",
    ["", ".", "decks/", "../outside.pptx", "decks/../../outside.pptx", "/tmp/outside.pptx"],
)
async def test_local_storage_rejects_invalid_keys(tmp_path: Path, key: str):
    storage = LocalDeckFileStorage(tmp_path)

    with pytest.raises(ValueError, match="Invalid storage key"):
        await storage.put(key, b"content")


@pytest.mark.asyncio
async def test_local_storage_list_keys_does_not_follow_outside_symlinks(tmp_path: Path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.pptx").write_bytes(b"secret")
    (root / "decks").mkdir(parents=True)
    (root / "decks" / "inside.pptx").write_bytes(b"inside")
    (root / "decks" / "outside-link").symlink_to(outside, target_is_directory=True)
    (root / "decks" / "file-link.pptx").symlink_to(outside / "secret.pptx")
    storage = LocalDeckFileStorage(root)

    assert await storage.list_keys("decks/") == ["decks/inside.pptx"]


@pytest.mark.asyncio
async def test_local_storage_rejects_key_through_symlink(tmp_path: Path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    storage = LocalDeckFileStorage(root)

    with pytest.raises(ValueError, match="Invalid storage key"):
        await storage.put("linked/version.pptx", b"content")


@pytest.fixture
def gcs_storage():
    client = MagicMock()
    bucket = MagicMock()
    client.bucket.return_value = bucket
    return GCSDeckFileStorage("deck-bucket", client=client), bucket


def test_gcs_storage_uses_configured_bucket_by_default(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(settings, "gcs_bucket", "configured-bucket")

    storage = GCSDeckFileStorage(client=client)
    storage._bucket()

    client.bucket.assert_called_once_with("configured-bucket")


@pytest.mark.asyncio
async def test_gcs_put_is_immutable_and_sets_pptx_content_type(gcs_storage):
    storage, bucket = gcs_storage
    blob = bucket.blob.return_value

    await storage.put("decks/d1/versions/v1.pptx", b"pptx")

    blob.upload_from_string.assert_called_once_with(
        b"pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        if_generation_match=0,
    )


@pytest.mark.asyncio
async def test_gcs_put_translates_precondition_failure(gcs_storage):
    storage, bucket = gcs_storage
    bucket.blob.return_value.upload_from_string.side_effect = PreconditionFailed("exists")

    with pytest.raises(FileExistsError):
        await storage.put("decks/d1/versions/v1.pptx", b"pptx")


@pytest.mark.asyncio
async def test_gcs_read_exists_and_list(gcs_storage):
    storage, bucket = gcs_storage
    blob = bucket.blob.return_value
    blob.download_as_bytes.return_value = b"pptx"
    blob.exists.return_value = True
    bucket.list_blobs.return_value = [
        SimpleNamespace(name="decks/d2.pptx"),
        SimpleNamespace(name="decks/d1.pptx"),
    ]

    assert await storage.read("decks/d1.pptx") == b"pptx"
    assert await storage.exists("decks/d1.pptx") is True
    assert await storage.list_keys("decks/") == ["decks/d1.pptx", "decks/d2.pptx"]
    bucket.list_blobs.assert_called_once_with(prefix="decks/")


@pytest.mark.asyncio
async def test_gcs_delete_ignores_not_found(gcs_storage):
    storage, bucket = gcs_storage
    bucket.blob.return_value.delete.side_effect = NotFound("missing")

    await storage.delete("decks/missing.pptx")

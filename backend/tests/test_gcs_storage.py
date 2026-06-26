from unittest.mock import MagicMock, patch

import pytest

from app.services.platform.storage import GCSStorageBackend


@pytest.mark.asyncio
async def test_gcs_upload_pptx_returns_signed_url():
    bucket = MagicMock()
    blob = MagicMock()
    blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-export.pptx"
    bucket.blob.return_value = blob

    backend = GCSStorageBackend(bucket_name="test-bucket", client=MagicMock())
    backend._client.bucket.return_value = bucket

    url = await backend.upload_pptx("session-123", b"pptx-content")

    assert url == "https://storage.googleapis.com/signed-export.pptx"
    bucket.blob.assert_called_once_with("exports/session-123.pptx")
    blob.upload_from_file.assert_called_once()
    blob.generate_signed_url.assert_called_once()


def test_gcs_get_local_path_returns_none():
    backend = GCSStorageBackend(bucket_name="test-bucket", client=MagicMock())
    assert backend.get_local_path("test.pptx") is None


@patch("app.services.platform.storage.Blob")
def test_gcs_generate_signed_url(mock_blob_cls):
    bucket = MagicMock()
    blob = MagicMock()
    blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-url"
    mock_blob_cls.return_value = blob

    backend = GCSStorageBackend(bucket_name="test-bucket", client=MagicMock())
    backend._client.bucket.return_value = bucket

    url = backend.generate_signed_url("exports/session-123.pptx", expiry_minutes=30)
    assert url == "https://storage.googleapis.com/signed-url"
    mock_blob_cls.assert_called_once_with("exports/session-123.pptx", bucket)
    blob.generate_signed_url.assert_called_once()

import time
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Protocol

from google.cloud import storage as gcs
from google.cloud.storage import Blob

from app.config import settings


class StorageBackend(Protocol):
    async def upload_pptx(self, session_id: str, content: bytes, base_url: str | None = None) -> str: ...
    def get_local_path(self, filename: str, max_age_seconds: int | None = None) -> Path | None: ...
    def purge_expired(self, max_age_seconds: int) -> int: ...
    def generate_signed_url(self, blob_path: str, expiry_minutes: int = 30) -> str: ...


class StorageService:
    """Local filesystem storage backend."""

    def __init__(self, bucket_name: str = "slideforge-temp", export_dir: str | None = None):
        self.bucket_name = bucket_name
        self.export_dir = Path(export_dir or settings.local_export_dir)

    async def upload_pptx(self, session_id: str, content: bytes, base_url: str | None = None) -> str:
        filename = f"{session_id}.pptx"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        path = self.export_dir / filename
        path.write_bytes(content)
        prefix = (settings.api_base_url or base_url or "").rstrip("/")
        return f"{prefix}/api/v1/download/{filename}"

    def get_local_path(self, filename: str, max_age_seconds: int | None = None) -> Path | None:
        if Path(filename).name != filename:
            return None
        path = self.export_dir / filename
        if not path.exists():
            return None
        if max_age_seconds is not None and time.time() - path.stat().st_mtime > max_age_seconds:
            path.unlink()
            return None
        return path

    def purge_expired(self, max_age_seconds: int) -> int:
        now = time.time()
        count = 0
        for path in self.export_dir.glob("*"):
            if (
                path.is_file()
                and path.suffix == ".pptx"
                and now - path.stat().st_mtime > max_age_seconds
            ):
                path.unlink()
                count += 1
        return count

    def generate_signed_url(self, blob_path: str, expiry_minutes: int = 30) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
        return f"{blob_path}?expires={expires_at.isoformat()}"


class GCSStorageBackend:
    def __init__(self, bucket_name: str | None = None, client: gcs.Client | None = None):
        self.bucket_name = bucket_name or settings.gcs_bucket
        self._client = client or gcs.Client(project=settings.gcp_project_id)

    def _bucket(self) -> gcs.Bucket:
        return self._client.bucket(self.bucket_name)

    async def upload_pptx(self, session_id: str, content: bytes, base_url: str | None = None) -> str:
        blob = self._bucket().blob(f"exports/{session_id}.pptx")
        blob.upload_from_file(BytesIO(content), content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=settings.signed_url_expiry_minutes),
            method="GET",
        )
        return url

    def get_local_path(self, filename: str, max_age_seconds: int | None = None) -> Path | None:
        return None

    def purge_expired(self, max_age_seconds: int) -> int:
        return 0

    def generate_signed_url(self, blob_path: str, expiry_minutes: int = 30) -> str:
        blob = Blob(blob_path, self._bucket())
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiry_minutes),
            method="GET",
        )
        return url

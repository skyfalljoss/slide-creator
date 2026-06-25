import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings


class StorageService:
    def __init__(self, bucket_name: str = "slideforge-temp", export_dir: str | None = None):
        self.bucket_name = bucket_name
        self.export_dir = Path(export_dir or settings.local_export_dir)

    async def upload_pptx(self, session_id: str, content: bytes, base_url: str | None = None) -> str:
        filename = f"{session_id}.pptx"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        path = self.export_dir / filename
        path.write_bytes(content)
        # Prefer an explicitly configured public base URL (e.g. behind a proxy);
        # otherwise fall back to the request's own base URL so the download link
        # points at the backend host rather than resolving against the frontend.
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

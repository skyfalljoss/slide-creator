import os
import time

from app.services.storage import StorageService
from app.services.uploads import UploadService


def test_storage_purge_expired_exports(tmp_path):
    service = StorageService(export_dir=tmp_path)
    path = tmp_path / "old.pptx"
    path.write_bytes(b"old")
    old = time.time() - 3600
    os.utime(path, (old, old))

    assert service.purge_expired(max_age_seconds=1) == 1
    assert not path.exists()


def test_storage_purge_preserves_unrelated_files_and_directories(tmp_path):
    service = StorageService(export_dir=tmp_path)
    export_path = tmp_path / "old.pptx"
    keep_path = tmp_path / "keep.txt"
    keep_dir = tmp_path / "keep-dir"
    export_path.write_bytes(b"old")
    keep_path.write_text("keep")
    keep_dir.mkdir()
    old = time.time() - 3600
    os.utime(export_path, (old, old))
    os.utime(keep_path, (old, old))
    os.utime(keep_dir, (old, old))

    assert service.purge_expired(max_age_seconds=1) == 1
    assert not export_path.exists()
    assert keep_path.exists()
    assert keep_dir.exists()


def test_storage_purge_preserves_fresh_exports(tmp_path):
    service = StorageService(export_dir=tmp_path)
    path = tmp_path / "fresh.pptx"
    path.write_bytes(b"fresh")

    assert service.purge_expired(max_age_seconds=3600) == 0
    assert path.exists()


def test_uploads_purge_expired_files(tmp_path):
    service = UploadService(upload_dir=tmp_path)
    path = tmp_path / "old.csv"
    path.write_text("a,b\n1,2\n")
    old = time.time() - 3600
    os.utime(path, (old, old))

    assert service.purge_expired(max_age_seconds=1) == 1
    assert not path.exists()


def test_uploads_purge_preserves_unrelated_files_and_directories(tmp_path):
    service = UploadService(upload_dir=tmp_path)
    csv_path = tmp_path / "old.csv"
    xlsx_path = tmp_path / "old.xlsx"
    keep_path = tmp_path / "keep.txt"
    keep_dir = tmp_path / "keep-dir"
    csv_path.write_text("a,b\n1,2\n")
    xlsx_path.write_bytes(b"old")
    keep_path.write_text("keep")
    keep_dir.mkdir()
    old = time.time() - 3600
    os.utime(csv_path, (old, old))
    os.utime(xlsx_path, (old, old))
    os.utime(keep_path, (old, old))
    os.utime(keep_dir, (old, old))

    assert service.purge_expired(max_age_seconds=1) == 2
    assert not csv_path.exists()
    assert not xlsx_path.exists()
    assert keep_path.exists()
    assert keep_dir.exists()


def test_uploads_purge_preserves_fresh_uploads(tmp_path):
    service = UploadService(upload_dir=tmp_path)
    path = tmp_path / "fresh.csv"
    path.write_text("a,b\n1,2\n")

    assert service.purge_expired(max_age_seconds=3600) == 0
    assert path.exists()


async def test_upload_pptx_uses_request_base_url_when_api_base_url_unset(tmp_path, monkeypatch):
    from app.services import storage as storage_mod

    monkeypatch.setattr(storage_mod.settings, "api_base_url", "")
    service = StorageService(export_dir=tmp_path)
    url = await service.upload_pptx("sess-123", b"PKdata", base_url="http://localhost:8000/")

    assert url == "http://localhost:8000/api/v1/download/sess-123.pptx"
    assert (tmp_path / "sess-123.pptx").exists()


async def test_upload_pptx_prefers_configured_api_base_url(tmp_path, monkeypatch):
    from app.services import storage as storage_mod

    monkeypatch.setattr(storage_mod.settings, "api_base_url", "https://api.example.com")
    service = StorageService(export_dir=tmp_path)
    url = await service.upload_pptx("sess-123", b"PKdata", base_url="http://localhost:8000/")

    assert url == "https://api.example.com/api/v1/download/sess-123.pptx"

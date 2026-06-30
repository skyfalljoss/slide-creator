import hashlib
import json
import os
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from uuid import uuid4

import httpx
import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from pptx import Presentation

from app import dependencies
from app.main import app
from app.services.platform.database import Database
from app.services.platform.deck_files import LocalDeckFileStorage
from app.services.platform.deck_repository import DeckRepository
from app.services.platform.deck_versions import DeckVersionService
from app.services.platform.onlyoffice import OnlyOfficeService


pytestmark = pytest.mark.onlyoffice
SECRET = "onlyoffice-smoke-secret-at-least-thirty-two-bytes"


def _pptx_bytes(slides: int) -> bytes:
    presentation = Presentation()
    for _ in range(slides):
        presentation.slides.add_slide(presentation.slide_layouts[0])
    output = BytesIO()
    presentation.save(output)
    return output.getvalue()


@contextmanager
def _fixture_server(content: bytes):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/edited.pptx":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.presentationml.presentation")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.skipif(not os.getenv("ONLYOFFICE_SMOKE_URL"), reason="ONLYOFFICE_SMOKE_URL is not set")
async def test_real_onlyoffice_docs_api_and_force_save_callback(tmp_path):
    docs_url = os.environ["ONLYOFFICE_SMOKE_URL"].rstrip("/")
    async with httpx.AsyncClient(timeout=10) as probe:
        response = await probe.get(f"{docs_url}/web-apps/apps/api/documents/api.js")
    assert response.status_code == 200
    assert b"DocsAPI" in response.content

    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'smoke.db'}")
    await database.create_schema()
    repository = DeckRepository(database)
    storage = LocalDeckFileStorage(tmp_path / "files")
    deck_id, version_id = str(uuid4()), str(uuid4())
    initial = _pptx_bytes(1)
    key = f"decks/{deck_id}/versions/{version_id}.pptx"
    await storage.put(key, initial)
    await repository.create_with_initial_version(
        deck_id=deck_id,
        version_id=version_id,
        owner_id="local-user",
        name="ONLYOFFICE smoke",
        deck_type="sales",
        theme="minimalist",
        aspect_ratio="16:9",
        generation_payload={"slides": []},
        storage_key=key,
        sha256=hashlib.sha256(initial).hexdigest(),
        size_bytes=len(initial),
    )
    edited = _pptx_bytes(2)
    with _fixture_server(edited) as fixture_url:
        download_client = httpx.AsyncClient()
        onlyoffice = OnlyOfficeService(
            public_url=docs_url,
            api_base_url="http://test",
            internal_url=fixture_url,
            jwt_secret=SECRET,
            file_token_ttl_seconds=300,
            max_file_bytes=len(edited) + 100,
            enabled=True,
            download_client=download_client,
        )
        versions = DeckVersionService(repository, storage, None, len(edited) + 100, 5)
        editor_config = onlyoffice.build_editor_config(
            deck=await repository.get(deck_id, "local-user"),
            user_id="local-user",
            user_name="Local User",
        )
        assert editor_config.document_server_url == docs_url
        assert editor_config.config["documentType"] == "slide"
        app.dependency_overrides[dependencies.get_onlyoffice_service] = lambda: onlyoffice
        app.dependency_overrides[dependencies.get_deck_version_service] = lambda: versions
        body = {
            "key": f"{deck_id}-{version_id}",
            "status": 6,
            "url": f"{fixture_url}/edited.pptx",
            "userdata": "smoke-force-save",
        }
        authorization = jwt.encode({"payload": body}, SECRET, algorithm="HS256")
        callback_token = onlyoffice.create_scoped_token(
            subject="local-user",
            deck_id=deck_id,
            version_id=version_id,
            purpose="callback",
        )
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                callback = await client.post(
                    f"/api/v1/decks/{deck_id}/callback?token={callback_token}",
                    content=json.dumps(body),
                    headers={
                        "Authorization": f"Bearer {authorization}",
                        "Content-Type": "application/json",
                    },
                )
        finally:
            app.dependency_overrides.clear()
            await download_client.aclose()

    deck = await repository.get(deck_id, "local-user")
    saved = await storage.read(deck.current_version.storage_key)
    try:
        assert callback.status_code == 200 and callback.json() == {"error": 0}
        assert deck.current_version.version_number == 2
        assert len(Presentation(BytesIO(saved)).slides) == 2
    finally:
        await repository.delete(deck_id, "local-user")
        await database.dispose()

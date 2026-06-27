# Native PPTX Editing with ONLYOFFICE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every generated deck as a versioned PPTX and replace the custom editor with a focused, full-screen ONLYOFFICE Presentation Editor.

**Architecture:** PostgreSQL stores deck/version metadata while local filesystem or GCS stores immutable PPTX objects. FastAPI renders version 1, issues signed ONLYOFFICE configurations and file tokens, handles force-save callbacks, and exposes version/restore/download APIs; React hosts the editor and polls the persisted version after saves. The internal deployment uses Docker Compose on one GCE VM with PostgreSQL 16 and ONLYOFFICE Docs Community 9.4.

**Tech Stack:** FastAPI, Python 3.11, SQLAlchemy 2 async, Alembic, PostgreSQL 16, PyJWT, httpx, Google Cloud Storage, python-pptx, React 19, TypeScript 6, TanStack Query 5, ONLYOFFICE Docs Community 9.4, Docker Compose, Nginx.

---

## Execution precondition

The repository currently has user-owned uncommitted changes across the generation engine, preview renderer, deck persistence, and frontend editor. Before implementing this plan:

1. Run `git status --short` and preserve the output in the execution log.
2. Do not discard or overwrite those changes.
3. If the user has committed them, create an isolated worktree from that commit with `superpowers:using-git-worktrees`.
4. If they remain uncommitted, execute in the existing tree and inspect every overlapping diff before editing. Do not stage unrelated files in the commits below.

## File map

### Backend database and storage

- Create `backend/app/services/platform/database.py`: async SQLAlchemy engine/session lifecycle.
- Create `backend/app/services/platform/deck_models.py`: `DeckRow` and `DeckVersionRow` ORM definitions.
- Create `backend/app/services/platform/deck_repository.py`: PostgreSQL/SQLAlchemy repository for deck metadata and version transactions.
- Preserve `backend/app/services/platform/deck_store.py` until the API cutover in Task 8 so existing uncommitted SQLite work remains recoverable.
- Create `backend/app/services/platform/deck_files.py`: immutable local/GCS PPTX object storage.
- Create `backend/app/services/presentation/pptx_validation.py`: reusable PPTX/OpenXML validation extracted from export.
- Create `backend/app/services/platform/deck_versions.py`: initial version, callback version, restore, and retention orchestration.
- Create `backend/alembic.ini`, `backend/migrations/env.py`, and `backend/migrations/versions/20260626_01_deck_versions.py`: schema migration.

### Backend ONLYOFFICE and API

- Create `backend/app/services/platform/onlyoffice.py`: JWTs, editor config, callback URL validation, and callback download.
- Create `backend/app/routers/onlyoffice.py`: editor config, content, callback, status, versions, restore, and direct download routes.
- Modify `backend/app/routers/generate.py`: render and persist version 1 before returning.
- Modify `backend/app/routers/decks.py`: use owner-scoped repository and rename-only updates.
- Modify `backend/app/routers/export.py`: reuse PPTX validation while legacy export remains during migration.
- Modify `backend/app/config.py`, `backend/app/dependencies.py`, `backend/app/main.py`, and `backend/app/models/schemas.py`: configuration, DI, lifecycle, router, and contracts.

### Frontend

- Create `frontend/src/lib/onlyoffice.ts`: Docs API loader and global types.
- Create `frontend/src/components/editor/OnlyOfficeEditor.tsx`: editor lifecycle and event adapter.
- Create `frontend/src/components/editor/VersionHistoryDialog.tsx`: retained-version list and restore.
- Replace `frontend/src/pages/EditorPage.tsx`: focused editor header, status, download, and failure states.
- Modify `frontend/src/pages/CreatePage.tsx`: navigate directly to the persisted deck editor.
- Modify `frontend/src/pages/MyDecksPage.tsx`: direct persisted download.
- Modify `frontend/src/App.tsx`: render the editor outside the standard sidebar layout.
- Modify `frontend/src/lib/api.ts` and `frontend/src/types/index.ts`: new contracts.

### Deployment

- Create `backend/Dockerfile`, `frontend/Dockerfile`, `deploy/nginx.conf`, `compose.yaml`, and `.env.example`.
- Modify `Makefile` and `README.md`: local stack and deployment commands.

## Task 1: Add database, migration, and ONLYOFFICE configuration

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Create: `backend/app/services/platform/database.py`
- Create: `backend/app/services/platform/deck_models.py`
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/script.py.mako`
- Create: `backend/migrations/versions/20260626_01_deck_versions.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write failing configuration tests**

Add tests that instantiate `Settings` with explicit environment dictionaries and assert:

```python
def test_onlyoffice_defaults_are_safe_for_local_development():
    configured = Settings(_env_file=None)
    assert configured.database_url.startswith("sqlite+aiosqlite:///")
    assert configured.onlyoffice_public_url == "http://localhost:8080"
    assert configured.onlyoffice_internal_url == "http://onlyoffice"
    assert configured.onlyoffice_max_file_bytes == 50_000_000


def test_onlyoffice_secret_is_required_when_enabled():
    configured = Settings(_env_file=None, onlyoffice_enabled=True, onlyoffice_jwt_secret="")
    with pytest.raises(ConfigurationError, match="ONLYOFFICE_JWT_SECRET"):
        validate_settings(configured)
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `cd backend && uv run pytest tests/test_config.py -v`
Expected: FAIL because the database and ONLYOFFICE settings do not exist.

- [ ] **Step 3: Add dependencies and settings**

Add these dependencies, then run `cd backend && uv lock`:

```toml
"alembic>=1.16,<2",
"asyncpg>=0.30,<1",
"PyJWT>=2.10,<3",
"sqlalchemy[asyncio]>=2.0,<3",
```

Add these `Settings` fields:

```python
database_url: str = "sqlite+aiosqlite:///.data/deck_versions.db"
onlyoffice_enabled: bool = False
onlyoffice_public_url: str = "http://localhost:8080"
onlyoffice_internal_url: str = "http://onlyoffice"
onlyoffice_jwt_secret: str = ""
onlyoffice_file_token_ttl_seconds: int = 300
onlyoffice_max_file_bytes: int = 50_000_000
deck_version_retention: int = 5
```

Move configuration checks into `validate_settings(configured: Settings)` so tests do not mutate the module singleton. Require the JWT secret when ONLYOFFICE is enabled and a GCS bucket when durable storage uses GCS.

- [ ] **Step 4: Add async database lifecycle and ORM rows**

Implement `Database` with `create_async_engine`, `async_sessionmaker`, `session()`, `dispose()`, and a test-only `create_schema()` helper. Define:

```python
class DeckRow(Base):
    __tablename__ = "decks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(500))
    deck_type: Mapped[str] = mapped_column(String(64))
    theme: Mapped[str] = mapped_column(String(64))
    aspect_ratio: Mapped[str] = mapped_column(String(16))
    generation_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    current_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("deck_versions.id", use_alter=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeckVersionRow(Base):
    __tablename__ = "deck_versions"
    __table_args__ = (UniqueConstraint("deck_id", "version_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    deck_id: Mapped[str] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(32))
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 5: Add the Alembic migration**

The migration creates both tables, the owner/update indexes, the `(deck_id, version_number)` unique constraint, and the deferred `decks.current_version_id` foreign key. Its downgrade drops the current-version foreign key before dropping the version and deck tables.

Run: `cd backend && uv run alembic upgrade head`
Expected: both tables exist in the configured local database.

- [ ] **Step 6: Run tests and commit**

Run: `cd backend && uv run ruff check app/ tests/ && uv run pytest tests/test_config.py -v`
Expected: PASS.

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/config.py backend/app/services/platform/database.py backend/app/services/platform/deck_models.py backend/alembic.ini backend/migrations backend/tests/test_config.py
git commit -m "feat: add versioned deck database schema"
```

## Task 2: Implement immutable PPTX file storage and validation

**Files:**
- Create: `backend/app/services/platform/deck_files.py`
- Create: `backend/app/services/presentation/pptx_validation.py`
- Modify: `backend/app/routers/export.py`
- Test: `backend/tests/test_deck_files.py`
- Test: `backend/tests/test_pptx_validation.py`

- [ ] **Step 1: Write failing storage contract tests**

Use `tmp_path` and assert immutable key behavior:

```python
@pytest.mark.asyncio
async def test_local_storage_round_trip_and_delete(tmp_path):
    storage = LocalDeckFileStorage(tmp_path)
    await storage.put("decks/d1/versions/v1.pptx", b"first")
    assert await storage.read("decks/d1/versions/v1.pptx") == b"first"
    await storage.delete("decks/d1/versions/v1.pptx")
    assert not await storage.exists("decks/d1/versions/v1.pptx")


@pytest.mark.asyncio
async def test_local_storage_rejects_overwrite(tmp_path):
    storage = LocalDeckFileStorage(tmp_path)
    key = "decks/d1/versions/v1.pptx"
    await storage.put(key, b"first")
    with pytest.raises(FileExistsError):
        await storage.put(key, b"second")
```

- [ ] **Step 2: Write failing PPTX validation tests**

Reuse a minimal valid file rendered by `PptxEngine` and assert that plain bytes, empty ZIP packages, and packages without slides raise `InvalidPptxError`.

Run: `cd backend && uv run pytest tests/test_deck_files.py tests/test_pptx_validation.py -v`
Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement the storage protocol and local adapter**

Define the exact interface:

```python
class DeckFileStorage(Protocol):
    async def put(self, key: str, content: bytes) -> None:
        raise NotImplementedError

    async def read(self, key: str) -> bytes:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def exists(self, key: str) -> bool:
        raise NotImplementedError

    async def list_keys(self, prefix: str) -> list[str]:
        raise NotImplementedError
```

`LocalDeckFileStorage` resolves keys below a configured root, rejects traversal, creates parent directories, and writes with exclusive mode (`"xb"`) so versions cannot be overwritten. `list_keys("decks/")` returns normalized relative keys and never follows paths outside the root.

- [ ] **Step 4: Implement the GCS adapter**

`GCSDeckFileStorage` uses generation-match precondition `if_generation_match=0` for immutable uploads, downloads bytes, lists only the requested prefix, and ignores not-found during cleanup. Wrap synchronous Google client calls with `asyncio.to_thread`.

```python
await asyncio.to_thread(
    blob.upload_from_string,
    content,
    content_type=PPTX_CONTENT_TYPE,
    if_generation_match=0,
)
```

- [ ] **Step 5: Extract shared PPTX validation**

Define `InvalidPptxError(ValueError)` and move `_validate_pptx_bytes` from `routers/export.py` into `validate_pptx(content: bytes, max_bytes: int) -> None`. Validate maximum size, `PK` signature, required OpenXML parts, at least one slide XML part, and `Presentation(BytesIO(content))`. Make legacy export call this shared function and translate it to the existing `GenerationError` response.

- [ ] **Step 6: Verify and commit**

Run: `cd backend && uv run ruff check app/ tests/ && uv run pytest tests/test_deck_files.py tests/test_pptx_validation.py tests/test_export_deck_id.py -v`
Expected: PASS.

```bash
git add backend/app/services/platform/deck_files.py backend/app/services/presentation/pptx_validation.py backend/app/routers/export.py backend/tests/test_deck_files.py backend/tests/test_pptx_validation.py
git commit -m "feat: add immutable pptx file storage"
```

## Task 3: Add a version-aware repository alongside the SQLite store

**Files:**
- Create: `backend/app/services/platform/deck_repository.py`
- Modify: `backend/app/dependencies.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_deck_repository.py`

- [ ] **Step 1: Write failing repository tests**

Create an in-memory SQLite async `Database`, create ORM schema, and test owner scoping, atomic initial creation, monotonic versions, and retention selection:

```python
@pytest.mark.asyncio
async def test_create_deck_sets_version_one_current(repository):
    created = await repository.create_with_initial_version(
        deck_id="deck-1",
        version_id="version-1",
        owner_id="alice",
        name="Quarterly Review",
        deck_type="internal_6",
        theme="minimalist",
        aspect_ratio="16:9",
        generation_payload={"slides": []},
        storage_key="decks/deck-1/versions/version-1.pptx",
        sha256="a" * 64,
        size_bytes=1200,
    )
    assert created.current_version.id == "version-1"
    assert created.current_version.version_number == 1
    assert await repository.get("deck-1", "bob") is None
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `cd backend && uv run pytest tests/test_deck_repository.py -v`
Expected: FAIL because the SQLAlchemy repository does not exist.

- [ ] **Step 3: Define repository records and methods**

Use frozen dataclasses `DeckRecord`, `DeckSummaryRecord`, and `DeckVersionRecord`. Implement:

```python
async def create_with_initial_version(
    self, *, deck_id: str, version_id: str, owner_id: str, name: str,
    deck_type: str, theme: str, aspect_ratio: str,
    generation_payload: dict | None, storage_key: str, sha256: str,
    size_bytes: int,
) -> DeckRecord
async def get(deck_id: str, owner_id: str) -> DeckRecord | None
async def list_all(owner_id: str, search: str, deck_type: str, sort: str) -> list[DeckSummaryRecord]
async def rename(deck_id: str, owner_id: str, name: str) -> bool
async def delete(deck_id: str, owner_id: str) -> list[str]
async def list_versions(deck_id: str, owner_id: str) -> list[DeckVersionRecord]
async def append_version(
    self, *, deck_id: str, owner_id: str, version_id: str,
    storage_key: str, sha256: str, size_bytes: int, source: str,
    created_by: str, base_version_id: str | None = None,
    generation_payload: dict | None = None,
) -> DeckVersionRecord
async def version(deck_id: str, version_id: str, owner_id: str) -> DeckVersionRecord | None
async def stale_versions(deck_id: str, keep: int) -> list[DeckVersionRecord]
async def delete_version_rows(version_ids: list[str]) -> None
async def all_storage_keys() -> set[str]
```

`append_version` starts a transaction, locks the deck row on PostgreSQL, compares `base_version_id` with the current pointer for conflict/audit logging, computes `max(version_number) + 1`, inserts the row, and updates `current_version_id`. A stale base still creates a distinct auditable version; transaction order determines the current version. SQLite test execution serializes through the session transaction.

- [ ] **Step 4: Wire database and repository lifecycle**

Add cached `get_database()` and `get_deck_repository()` while retaining `get_deck_store()` for the legacy API until Task 8. FastAPI lifespan initializes the new database for local development; deployment runs Alembic before application startup. Tests call `create_schema()`. Dispose the async engine and shared `httpx.AsyncClient` during shutdown.

- [ ] **Step 5: Verify the legacy store remains untouched**

Run the existing `tests/test_deck_store.py` and `tests/test_decks_api.py` unchanged. They must still pass against `get_deck_store()` while the new repository tests exercise `get_deck_repository()`. This provides an explicit migration seam instead of mixing SQLite rows with the new schema.

- [ ] **Step 6: Verify and commit**

Run: `cd backend && uv run ruff check app/ tests/ && uv run pytest tests/test_deck_repository.py tests/test_deck_store.py tests/test_decks_api.py tests/test_dependencies.py -v`
Expected: PASS.

```bash
git add backend/app/services/platform/deck_repository.py backend/app/dependencies.py backend/app/main.py backend/tests/test_deck_repository.py
git commit -m "feat: add owner-scoped deck version repository"
```

## Task 4: Build the deck version service

**Files:**
- Create: `backend/app/services/platform/deck_versions.py`
- Modify: `backend/app/dependencies.py`
- Test: `backend/tests/test_deck_versions.py`

- [ ] **Step 1: Write failing initial-save and callback-save tests**

Use fake repository/storage objects to prove ordering and rollback:

```python
@pytest.mark.asyncio
async def test_create_generated_deck_stores_valid_version_one(service, repository, storage, slides):
    deck = await service.create_generated_deck(
        owner_id="alice",
        name="Generated",
        deck_type="sales_9",
        theme="minimalist",
        aspect_ratio="16:9",
        slides=slides,
    )
    stored = await storage.read(deck.current_version.storage_key)
    validate_pptx(stored, max_bytes=50_000_000)
    assert deck.current_version.version_number == 1


@pytest.mark.asyncio
async def test_repository_failure_removes_orphan_upload(service, repository, storage, slides):
    repository.fail_create = True
    with pytest.raises(RuntimeError):
        await service.create_generated_deck(
            owner_id="alice", name="Generated", deck_type="sales_9",
            theme="minimalist", aspect_ratio="16:9", slides=slides,
        )
    assert storage.keys == set()
```

- [ ] **Step 2: Write failing idempotency, restore, and retention tests**

Assert the same deck/checksum/source identity returns the existing version, restore copies selected bytes into a new immutable key, and a sixth version deletes only version 1 after metadata commits.

Run: `cd backend && uv run pytest tests/test_deck_versions.py -v`
Expected: FAIL because `DeckVersionService` does not exist.

- [ ] **Step 3: Implement initial deck persistence**

`create_generated_deck` renders with `PptxEngine`, validates bytes, generates deck/version UUIDs, uploads `decks/{deck_id}/versions/{version_id}.pptx`, and then calls `create_with_initial_version`. If the repository fails, delete that exact object and re-raise.

- [ ] **Step 4: Implement saved-version and restore paths**

Use these public methods:

```python
async def save_edited_version(
    self, *, deck_id: str, owner_id: str, content: bytes,
    base_version_id: str, callback_key: str, created_by: str,
) -> DeckVersionRecord

async def restore_version(
    self, *, deck_id: str, version_id: str, owner_id: str,
    created_by: str,
) -> DeckVersionRecord

async def save_slides_as_version(
    self, *, deck_id: str, owner_id: str, slides: list[SlideData],
    theme: str, aspect_ratio: str, created_by: str,
) -> DeckVersionRecord
```

Validate before upload. Compute SHA-256. Treat `(deck_id, callback_key, sha256)` as idempotent. Generate a new version UUID/storage key, upload, append metadata, and clean up the upload if metadata commit fails. `save_slides_as_version` exists only for the legacy Preview/API transition: it renders with `PptxEngine`, stores source `generated`, and updates generation provenance together with the new version.

- [ ] **Step 5: Implement post-commit retention**

After the new version becomes current, fetch versions older than the newest `settings.deck_version_retention`. Delete each object, then delete only the successfully removed metadata rows. Log and retain failed deletions for the next cleanup run; never fail the completed save.

- [ ] **Step 6: Verify and commit**

Run: `cd backend && uv run ruff check app/ tests/ && uv run pytest tests/test_deck_versions.py -v`
Expected: PASS.

```bash
git add backend/app/services/platform/deck_versions.py backend/app/dependencies.py backend/tests/test_deck_versions.py
git commit -m "feat: orchestrate versioned deck files"
```

## Task 5: Persist version 1 during generation

**Files:**
- Modify: `backend/app/models/schemas.py`
- Modify: `backend/app/routers/generate.py`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_schemas.py`
- Test: `backend/tests/test_generate_persistence.py`

- [ ] **Step 1: Write the failing generation persistence test**

Override `get_deck_version_service` with a fake and assert generation does not return until persistence finishes:

```python
@pytest.mark.asyncio
async def test_generate_returns_persisted_deck_id(client, fake_version_service):
    response = await client.post(
        "/api/v1/generate",
        headers={"X-User-Id": "alice"},
        json={"prompt": "Quarterly review", "deck_type": "internal_6"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["deck_id"] == "deck-persisted"
    assert body["editor_path"] == "/editor/deck-persisted"
    assert fake_version_service.calls[0]["owner_id"] == "alice"
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `cd backend && uv run pytest tests/test_generate_persistence.py -v`
Expected: FAIL because generation only creates an expiring session.

- [ ] **Step 3: Extend the response contract compatibly**

Use:

```python
class GenerateResponse(BaseModel):
    session_id: str
    deck_id: str
    editor_path: str
    slides: list[SlideData]
```

Keep `session_id` and `slides` during migration so Preview/refine routes remain functional.

- [ ] **Step 4: Persist after DLP and media resolution**

Inject `DeckVersionService`, call `create_generated_deck` after the final DLP scan, use the first slide title or `Untitled Deck`, and return the created ID/path. Create the legacy session after durable persistence, not before it. Audit both session ID and deck ID in structured metadata.

- [ ] **Step 5: Verify failure semantics**

Add a test where the version service raises `StorageError`; assert `/generate` returns the mapped 5xx response, no success payload is returned, and no session is created.

- [ ] **Step 6: Verify and commit**

Run: `cd backend && uv run ruff check app/ tests/ && uv run pytest tests/test_generate_persistence.py tests/test_api.py tests/test_schemas.py -v`
Expected: PASS.

```bash
git add backend/app/models/schemas.py backend/app/routers/generate.py backend/tests/test_generate_persistence.py backend/tests/test_api.py backend/tests/test_schemas.py
git commit -m "feat: persist generated pptx before editor navigation"
```

## Task 6: Implement ONLYOFFICE tokens, editor configuration, and secure content

**Files:**
- Create: `backend/app/services/platform/onlyoffice.py`
- Create: `backend/app/routers/onlyoffice.py`
- Modify: `backend/app/models/schemas.py`
- Modify: `backend/app/dependencies.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_onlyoffice_service.py`
- Test: `backend/tests/test_onlyoffice_api.py`

- [ ] **Step 1: Write failing token and configuration tests**

Freeze time and assert editor config fields:

```python
def test_editor_config_is_signed_for_current_version(service, deck):
    result = service.build_editor_config(deck=deck, user_id="alice", user_name="Alice")
    assert result.document_server_url == "http://localhost:8080"
    assert result.config["documentType"] == "slide"
    assert result.config["document"]["fileType"] == "pptx"
    assert result.config["document"]["key"] == f"{deck.id}-{deck.current_version.id}"
    assert result.config["editorConfig"]["customization"]["forcesave"] is True
    assert jwt.decode(result.config["token"], "test-secret", algorithms=["HS256"])["documentType"] == "slide"
```

Also assert expired tokens, wrong purpose, wrong deck/version, and wrong signatures are rejected.

- [ ] **Step 2: Write failing editor-config and content API tests**

Assert an owner receives config and PPTX bytes, another user gets 404, and expired content tokens get 401.

Run: `cd backend && uv run pytest tests/test_onlyoffice_service.py tests/test_onlyoffice_api.py -v`
Expected: FAIL because the integration does not exist.

- [ ] **Step 3: Implement scoped JWT helpers**

Create HS256 tokens with claims `sub`, `deck_id`, `version_id`, `purpose`, `iat`, and `exp`. Support `purpose` values `content` and `callback`. Decode with an explicit algorithm list and validate all identity claims before file access.

- [ ] **Step 4: Build the editor configuration**

Return a schema with `document_server_url` and `config`. The exact config is:

```python
config = {
    "document": {
        "fileType": "pptx",
        "key": f"{deck.id}-{version.id}",
        "title": f"{deck.name}.pptx",
        "url": content_url,
        "permissions": {"edit": True, "download": True, "print": True},
    },
    "documentType": "slide",
    "editorConfig": {
        "mode": "edit",
        "callbackUrl": callback_url,
        "user": {"id": user_id, "name": user_name},
        "customization": {"autosave": True, "forcesave": True},
    },
}
config["token"] = jwt.encode(config, secret, algorithm="HS256")
```

Use the public ONLYOFFICE URL for the browser script and internal FastAPI URLs for document fetch/callback when running in Compose.

- [ ] **Step 5: Add editor-config and content routes**

Add owner-scoped `GET /decks/{deck_id}/editor-config` and token-scoped `GET /decks/{deck_id}/content`. Stream bytes with PPTX media type, `Content-Disposition: inline`, `Cache-Control: private, no-store`, and no public GCS URL.

- [ ] **Step 6: Register, verify, and commit**

Register the router under `/api/v1`. Run:

`cd backend && uv run ruff check app/ tests/ && uv run pytest tests/test_onlyoffice_service.py tests/test_onlyoffice_api.py -v`
Expected: PASS.

```bash
git add backend/app/services/platform/onlyoffice.py backend/app/routers/onlyoffice.py backend/app/models/schemas.py backend/app/dependencies.py backend/app/main.py backend/tests/test_onlyoffice_service.py backend/tests/test_onlyoffice_api.py
git commit -m "feat: add secure onlyoffice editor configuration"
```

## Task 7: Handle force-save callbacks idempotently

**Files:**
- Modify: `backend/app/services/platform/onlyoffice.py`
- Modify: `backend/app/routers/onlyoffice.py`
- Modify: `backend/app/models/schemas.py`
- Test: `backend/tests/test_onlyoffice_callback.py`

- [ ] **Step 1: Write failing callback status tests**

Cover status `1` and `4` as no-op success, status `2` and `6` as save-bearing, and status `3` and `7` as save errors. A successful status `6` test must assert one new version and `{"error": 0}`.

- [ ] **Step 2: Write failing security and size tests**

Assert callback rejection for an invalid callback token, Authorization JWT mismatch, URL hostname outside `onlyoffice_internal_url`, redirect to another host, timeout, response exceeding `onlyoffice_max_file_bytes`, and invalid PPTX bytes.

Run: `cd backend && uv run pytest tests/test_onlyoffice_callback.py -v`
Expected: FAIL because the callback is absent.

- [ ] **Step 3: Add the callback schema and bounded downloader**

Define:

```python
class OnlyOfficeCallback(BaseModel):
    key: str
    status: int
    url: str | None = None
    users: list[str] = Field(default_factory=list)
    userdata: str | None = None
```

The downloader uses `httpx.AsyncClient.stream`, disables redirects, compares parsed scheme/hostname/port to the configured internal origin, checks `Content-Length`, and stops reading when the accumulated body exceeds the maximum.

- [ ] **Step 4: Implement callback authentication and status dispatch**

Validate the scoped callback token from the callback URL. Validate the ONLYOFFICE Authorization bearer JWT against the configured secret and request body when enabled. Derive `owner_id`, `created_by`, and `base_version_id` from the trusted callback token, never from `body.users`. For status `2` or `6`, require `url`, download, and call `save_edited_version` with callback key `f"{body.key}:{body.status}:{body.userdata or ''}"`. Return `{"error": 0}` only after persistence succeeds.

- [ ] **Step 5: Add idempotency and failure mapping tests**

Send the identical callback twice and assert one version row. Make storage fail and assert the old current version is unchanged and the callback returns `{"error": 1}` with an internal structured error log that excludes URLs and tokens.

- [ ] **Step 6: Verify and commit**

Run: `cd backend && uv run ruff check app/ tests/ && uv run pytest tests/test_onlyoffice_callback.py tests/test_onlyoffice_api.py -v`
Expected: PASS.

```bash
git add backend/app/services/platform/onlyoffice.py backend/app/routers/onlyoffice.py backend/app/models/schemas.py backend/tests/test_onlyoffice_callback.py
git commit -m "feat: persist onlyoffice force-save callbacks"
```

## Task 8: Add version history, restore, status, rename, and direct download APIs

**Files:**
- Modify: `backend/app/models/schemas.py`
- Modify: `backend/app/routers/onlyoffice.py`
- Modify: `backend/app/routers/decks.py`
- Modify: `backend/app/dependencies.py`
- Test: `backend/tests/test_deck_versions_api.py`
- Modify: `backend/tests/test_decks_api.py`

- [ ] **Step 1: Write failing route tests**

Create six versions and assert the API retains/list the newest five, returns current status, restores version 2 as version 7, renames the deck, and downloads bytes from version 7. Assert cross-user requests return 404.

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && uv run pytest tests/test_deck_versions_api.py tests/test_decks_api.py -v`
Expected: FAIL because the routes and response types are absent.

- [ ] **Step 3: Add response contracts**

Define `DeckVersionResponse`, `ListDeckVersionsResponse`, `DeckStatusResponse`, `RestoreVersionResponse`, and `RenameDeckRequest`. Version responses expose IDs, number, source, creator, size, checksum, and timestamp but never `storage_key`.

- [ ] **Step 4: Cut deck CRUD over to the owner-scoped repository**

Change list/get/delete/rename to use `get_deck_repository()` and `get_user_id(request)`. Continue returning `slides` from `generation_payload` in `DeckDetail` until Preview is retired. Keep `POST /decks` compatible during the frontend migration by passing its slide payload to `DeckVersionService.create_generated_deck`, so even legacy saves create a valid authoritative version-1 PPTX. If legacy `PUT /decks/{id}` contains `slides`, render those slides and append a new persisted PPTX version before applying a name change; mark the version source as `generated`. Remove `get_deck_store()` from active route dependencies but retain the module for the Task 13 migration utility.

- [ ] **Step 5: Implement version and download routes**

Add:

```text
GET  /decks/{deck_id}/status
GET  /decks/{deck_id}/versions
POST /decks/{deck_id}/versions/{version_id}/restore
GET  /decks/{deck_id}/download
PATCH /decks/{deck_id}
```

Direct download returns current persisted bytes with attachment filename derived from a sanitized deck name. Restore invokes `DeckVersionService.restore_version` and returns the new current version.

- [ ] **Step 6: Preserve delete semantics**

Deck deletion removes the owner-scoped database record, then best-effort deletes every returned storage key. A storage cleanup failure is logged and retried by orphan cleanup; the deck remains deleted from the user's view.

- [ ] **Step 7: Verify and commit**

Run: `cd backend && uv run ruff check app/ tests/ && uv run pytest tests/test_deck_versions_api.py tests/test_decks_api.py -v`
Expected: PASS.

```bash
git add backend/app/models/schemas.py backend/app/routers/onlyoffice.py backend/app/routers/decks.py backend/app/dependencies.py backend/tests/test_deck_versions_api.py backend/tests/test_decks_api.py
git commit -m "feat: expose deck history restore and download"
```

## Task 9: Add frontend API contracts and ONLYOFFICE loader

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/onlyoffice.ts`
- Modify: `frontend/src/lib/api.test.ts`
- Test: `frontend/src/lib/onlyoffice.test.ts`

- [ ] **Step 1: Write failing API and loader tests**

Assert `getEditorConfig`, `getDeckStatus`, `listDeckVersions`, `restoreDeckVersion`, `renameDeck`, and `deckDownloadUrl` use the exact routes from Task 8. In jsdom, call the loader twice and assert one script tag is appended and both promises resolve after `window.DocsAPI` appears.

- [ ] **Step 2: Run tests and verify failure**

Run: `cd frontend && pnpm test -- src/lib/api.test.ts src/lib/onlyoffice.test.ts`
Expected: FAIL because the functions/types do not exist.

- [ ] **Step 3: Add TypeScript contracts**

Add:

```typescript
export interface GenerateResponse {
  session_id: string
  deck_id: string
  editor_path: string
  slides: SlideData[]
}

export interface OnlyOfficeEditorConfig {
  document_server_url: string
  config: Record<string, unknown>
}

export interface DeckVersion {
  id: string
  version_number: number
  source: 'generated' | 'onlyoffice_save' | 'restore'
  created_by: string
  created_at: string
  size_bytes: number
  sha256: string
}

export interface DeckStatus {
  current_version_id: string
  current_version_number: number
  updated_at: string
}
```

- [ ] **Step 4: Implement API functions**

Add a generic `patchRequest` and these exact exports:

```typescript
getEditorConfig(deckId: string): Promise<OnlyOfficeEditorConfig>
getDeckStatus(deckId: string): Promise<DeckStatus>
listDeckVersions(deckId: string): Promise<{ versions: DeckVersion[] }>
restoreDeckVersion(deckId: string, versionId: string): Promise<DeckStatus>
renameDeck(deckId: string, name: string): Promise<DeckDetail>
deckDownloadUrl(deckId: string): string
```

- [ ] **Step 5: Implement the Docs API loader**

Declare the minimal `window.DocsAPI.DocEditor` constructor and editor `destroyEditor()` method. `loadOnlyOfficeApi(baseUrl)` normalizes the URL, keys cached promises by base URL, appends `/web-apps/apps/api/documents/api.js`, rejects on `onerror`, and resolves only when `window.DocsAPI?.DocEditor` exists.

- [ ] **Step 6: Verify and commit**

Run: `cd frontend && pnpm test -- src/lib/api.test.ts src/lib/onlyoffice.test.ts && pnpm build`
Expected: PASS.

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src/lib/onlyoffice.ts frontend/src/lib/onlyoffice.test.ts
git commit -m "feat: add onlyoffice frontend contracts"
```

## Task 10: Replace the custom editor with the ONLYOFFICE host page

**Files:**
- Create: `frontend/src/components/editor/OnlyOfficeEditor.tsx`
- Create: `frontend/src/components/editor/VersionHistoryDialog.tsx`
- Replace: `frontend/src/pages/EditorPage.tsx`
- Replace: `frontend/src/pages/EditorPage.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write failing editor lifecycle tests**

Mock the loader and constructor. Assert the editor receives the backend config, `destroyEditor()` runs on unmount, `onDocumentStateChange({data: true})` displays `Unsaved`, and transition to `false` polls status until the version number increases before displaying `Saved as version 2`.

- [ ] **Step 2: Write failing failure and navigation tests**

Assert editor-config failure shows Retry and Back, download is disabled while save confirmation is pending, `beforeunload` prevents navigation while dirty/pending, and no warning occurs after persistence confirmation.

Run: `cd frontend && pnpm test -- src/pages/EditorPage.test.tsx`
Expected: FAIL against the current preview-and-properties editor.

- [ ] **Step 3: Implement `OnlyOfficeEditor`**

The component owns a unique container ID, loads the Docs API, instantiates `new window.DocsAPI.DocEditor(containerId, mergedConfig)`, merges event handlers without mutating the query result, reports dirty/error state through callbacks, fills its parent, and destroys the instance on cleanup.

- [ ] **Step 4: Implement the focused `EditorPage`**

Load deck, editor config, and status with TanStack Query. Render a 48px header containing Back, editable name, status, Versions, and Download. Render ONLYOFFICE in the remaining `calc(100vh - 48px)` area. Poll status every second only while awaiting save confirmation and stop after success, error, unmount, or 30 seconds.

- [ ] **Step 5: Implement version history and restore**

`VersionHistoryDialog` lists retained versions newest-first. Restore requires a confirmation button, invokes `restoreDeckVersion`, invalidates deck/config/status/version queries, and remounts `OnlyOfficeEditor` keyed by `current_version_id`.

- [ ] **Step 6: Move the editor outside standard layout**

In `App.tsx`, place `/editor/:deckId` as a top-level route next to `/login`; keep Create, Preview, Export, and My Decks under `<Layout>`. This prevents the global sidebar/header from consuming editor space.

- [ ] **Step 7: Verify and commit**

Run: `cd frontend && pnpm test -- src/pages/EditorPage.test.tsx && pnpm lint && pnpm build`
Expected: PASS.

```bash
git add frontend/src/components/editor frontend/src/pages/EditorPage.tsx frontend/src/pages/EditorPage.test.tsx frontend/src/App.tsx
git commit -m "feat: embed onlyoffice presentation editor"
```

## Task 11: Route creation and My Decks through persisted PPTX files

**Files:**
- Modify: `frontend/src/pages/CreatePage.tsx`
- Modify: `frontend/src/pages/CreatePage.test.tsx`
- Modify: `frontend/src/pages/MyDecksPage.tsx`
- Create: `frontend/src/pages/MyDecksPage.test.tsx`
- Modify: `frontend/src/pages/PreviewPage.tsx`
- Modify: `frontend/src/state/DeckContext.tsx`

- [ ] **Step 1: Update failing Create page expectations**

Mock `generate` to return `deck_id` and `editor_path`. Assert Create calls `generate` once, does not call `saveDeck`, stores compatibility session state, and navigates to `/editor/deck-1` only after the response resolves.

- [ ] **Step 2: Add failing My Decks download test**

Assert Download uses `/api/v1/decks/deck-1/download` and does not call legacy `/export` or regenerate a PPTX.

Run: `cd frontend && pnpm test -- src/pages/CreatePage.test.tsx src/pages/MyDecksPage.test.tsx`
Expected: FAIL because Create still performs a second save and navigates to Preview, while My Decks calls export.

- [ ] **Step 3: Simplify Create flow**

Remove the `saveDeck` mutation from `CreatePage`. After generation, keep `setGeneratedDeck` only for temporary Preview compatibility, set `savedDeckId` from `result.deck_id`, and call `navigate(result.editor_path)`.

- [ ] **Step 4: Use direct persisted download in My Decks**

Remove the export mutation and open `deckDownloadUrl(deck.id)` in the same browser context. Disable nothing for generation because the file already exists. Preserve Edit and Delete behavior.

- [ ] **Step 5: Keep Preview explicitly legacy**

Remove Preview's responsibility for first persistence. Its Save action may update legacy generation metadata only when entered through the legacy route; it must not overwrite the authoritative PPTX or appear in the default Create flow.

- [ ] **Step 6: Verify and commit**

Run: `cd frontend && pnpm test && pnpm lint && pnpm build`
Expected: PASS.

```bash
git add frontend/src/pages/CreatePage.tsx frontend/src/pages/CreatePage.test.tsx frontend/src/pages/MyDecksPage.tsx frontend/src/pages/MyDecksPage.test.tsx frontend/src/pages/PreviewPage.tsx frontend/src/state/DeckContext.tsx
git commit -m "feat: open persisted decks directly in editor"
```

## Task 12: Add Docker Compose and production-shaped internal deployment

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `deploy/nginx.conf`
- Create: `deploy/backup-postgres.sh`
- Create: `compose.yaml`
- Create: `.env.example`
- Modify: `Makefile`
- Modify: `README.md`

- [ ] **Step 1: Write the deployment configuration**

Create services:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: slideforge
      POSTGRES_USER: slideforge
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U slideforge"]

  onlyoffice:
    image: onlyoffice/documentserver:9.4.0.1
    environment:
      JWT_ENABLED: "true"
      JWT_SECRET: ${ONLYOFFICE_JWT_SECRET}
    shm_size: 2gb
    volumes:
      - onlyoffice-data:/var/www/onlyoffice/Data
      - onlyoffice-logs:/var/log/onlyoffice

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+asyncpg://slideforge:${POSTGRES_PASSWORD}@postgres:5432/slideforge
      ONLYOFFICE_ENABLED: "true"
      ONLYOFFICE_PUBLIC_URL: ${ONLYOFFICE_PUBLIC_URL}
      ONLYOFFICE_INTERNAL_URL: http://onlyoffice
      ONLYOFFICE_JWT_SECRET: ${ONLYOFFICE_JWT_SECRET}
    depends_on:
      postgres:
        condition: service_healthy
      onlyoffice:
        condition: service_started

  web:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend
      - onlyoffice
```

- [ ] **Step 2: Add container builds and reverse proxy**

The backend image installs locked dependencies with uv, runs `alembic upgrade head`, then starts Uvicorn. The frontend image builds with pnpm and serves static assets through Nginx. Nginx proxies `/api/` to `backend:8000` and `/onlyoffice/` to `onlyoffice:80`, including WebSocket upgrade headers and forwarded protocol/host headers. Add Compose health checks for FastAPI `/api/v1/health`, ONLYOFFICE `/healthcheck`, and Nginx `/` in addition to PostgreSQL.

- [ ] **Step 3: Add explicit environment documentation**

`.env.example` includes non-secret local defaults and names for `POSTGRES_PASSWORD`, `ONLYOFFICE_JWT_SECRET`, `ONLYOFFICE_PUBLIC_URL`, `GCP_PROJECT_ID`, `GCS_BUCKET`, `BACKUP_GCS_URI`, and `STORAGE_PROVIDER`. README requires generating both secrets, keeping `.env` untracked, provisioning an internal DNS name, and terminating HTTPS before production use.

`deploy/backup-postgres.sh` runs `pg_dump` through the Compose PostgreSQL service, compresses it, uploads it to `${BACKUP_GCS_URI}/slideforge-YYYYMMDDTHHMMSSZ.sql.gz`, and removes the local temporary file through a shell trap. The runbook installs it as a nightly systemd timer on the GCE VM and documents a restore drill command.

- [ ] **Step 4: Add operational commands**

Add Make targets:

```make
stack-up:
	docker compose up --build -d

stack-down:
	docker compose down

stack-logs:
	docker compose logs -f backend onlyoffice web

migrate:
	cd backend && uv run alembic upgrade head
```

- [ ] **Step 5: Validate deployment configuration**

Run: `docker compose config`
Expected: exit 0 with four services and no unresolved required variables when using `.env.example` values.

Run: `docker compose up --build -d postgres onlyoffice backend web`
Expected: PostgreSQL healthy, FastAPI health returns 200, ONLYOFFICE `/healthcheck` returns `true`, and the frontend loads.

- [ ] **Step 6: Commit**

```bash
git add backend/Dockerfile frontend/Dockerfile deploy/nginx.conf deploy/backup-postgres.sh compose.yaml .env.example Makefile README.md
git commit -m "ops: add internal onlyoffice deployment stack"
```

## Task 13: Add migration utility and end-to-end smoke coverage

**Files:**
- Create: `backend/scripts/migrate_sqlite_decks.py`
- Create: `backend/scripts/cleanup_orphan_deck_files.py`
- Create: `backend/tests/test_migrate_sqlite_decks.py`
- Create: `backend/tests/test_cleanup_orphan_deck_files.py`
- Create: `backend/tests/test_postgres_deck_repository.py`
- Create: `backend/tests/test_onlyoffice_smoke.py`
- Modify: `backend/pyproject.toml`
- Modify: `README.md`

- [ ] **Step 1: Write a failing legacy migration test**

Create a temporary legacy SQLite `decks` table with one slide-JSON deck, run the migration function with fake version storage/repository, and assert it renders a valid version-1 PPTX while preserving ID, name, deck type, theme, aspect ratio, timestamps, and generation payload.

- [ ] **Step 2: Implement idempotent migration**

The script accepts `--sqlite-path` and `--owner-id`, skips IDs already present in PostgreSQL, validates every rendered PPTX, and prints counts for migrated, skipped, and failed decks. One deck failure is reported without stopping other decks; the process exits nonzero when any deck fails.

- [ ] **Step 3: Add orphan cleanup with a grace period**

Write a failing test with repository keys `{v1, v2}` and storage keys `{v1, v2, orphan}`. Implement `cleanup_orphan_deck_files.py` to list `decks/`, compare against every repository `storage_key`, and delete only unreferenced objects older than 24 hours. Support `--dry-run` by default and require `--apply` for deletion. Print examined, retained, candidate, and deleted counts; return nonzero when a deletion fails.

- [ ] **Step 4: Add an opt-in PostgreSQL concurrency test**

Mark with `@pytest.mark.postgres` and skip unless `TEST_DATABASE_URL` is set. Start two independent async sessions that append versions to the same deck concurrently. Assert both commits succeed with distinct version numbers, no unique-constraint error occurs, and the current pointer selects one complete version. Repeat with the same callback/checksum and assert idempotency produces one row.

- [ ] **Step 5: Add an opt-in real ONLYOFFICE smoke test**

Mark with `@pytest.mark.onlyoffice` and skip unless `ONLYOFFICE_SMOKE_URL` is set. The test creates a valid PPTX, obtains editor config, confirms the Docs API endpoint is reachable, submits a fixture force-save callback pointing to an HTTP fixture server, and verifies the current version increments and downloads as a readable PPTX.

- [ ] **Step 6: Register the markers and document commands**

Add `onlyoffice: requires a running ONLYOFFICE Document Server` and `postgres: requires a running PostgreSQL integration database` to pytest markers. Document:

```bash
cd backend
uv run python scripts/migrate_sqlite_decks.py --sqlite-path .data/decks.db --owner-id local-user
uv run python scripts/cleanup_orphan_deck_files.py --dry-run
TEST_DATABASE_URL=postgresql+asyncpg://slideforge:slideforge@localhost:5432/slideforge uv run pytest -m postgres -v
ONLYOFFICE_SMOKE_URL=http://localhost:8080 uv run pytest -m onlyoffice -v
```

- [ ] **Step 7: Run full verification**

Run:

```bash
cd backend
uv run ruff check app/ tests/ scripts/
uv run pytest
cd ../frontend
pnpm lint
pnpm build
pnpm test
cd ..
docker compose config
```

Expected: all commands exit 0. The normal pytest suite skips the opt-in PostgreSQL concurrency and real ONLYOFFICE smoke tests when their environment variables are absent.

- [ ] **Step 8: Commit**

```bash
git add backend/scripts/migrate_sqlite_decks.py backend/scripts/cleanup_orphan_deck_files.py backend/tests/test_migrate_sqlite_decks.py backend/tests/test_cleanup_orphan_deck_files.py backend/tests/test_postgres_deck_repository.py backend/tests/test_onlyoffice_smoke.py backend/pyproject.toml README.md
git commit -m "test: cover onlyoffice migration and save flow"
```

## Completion criteria

- A successful generation response contains a durable `deck_id`; version 1 exists before the response is returned.
- The default frontend flow navigates directly from Create to the full-screen ONLYOFFICE editor.
- ONLYOFFICE loads the current stored PPTX and force-save creates exactly one new immutable version per unique callback/content checksum.
- Download returns the current stored PPTX without invoking `PptxEngine`.
- Version history retains five entries and restore creates a new current version.
- Cross-user deck/config/content/history/restore/download access is denied.
- Save failure never changes `current_version_id`.
- Backend Ruff and pytest, frontend lint/build/Vitest, Docker Compose validation, and the opt-in ONLYOFFICE smoke path pass.

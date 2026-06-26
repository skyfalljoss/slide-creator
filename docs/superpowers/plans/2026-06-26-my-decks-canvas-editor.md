# My Decks Page + Canvas-Based PPTX Editor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent My Decks page with deck listing/CRUD and a Fabric.js canvas editor for WYSIWYG slide editing before export.

**Architecture:** Backend gets a new SQLite-backed `DeckStore` service with 5 CRUD endpoints. Frontend gets two new pages (`/my-decks` and `/editor/:deckId`) plus a canvas bridge utility to map `SlideData` ↔ Fabric.js objects bidirectionally.

**Tech Stack:** Python/FastAPI/aiosqlite (backend), React/TypeScript/Fabric.js v6/TanStack Query (frontend)

---

## File Structure Map

| File | Responsibility |
|------|---------------|
| **Backend (new)** | |
| `backend/app/services/platform/deck_store.py` | Async SQLite CRUD for decks |
| `backend/app/routers/decks.py` | 5 REST endpoints for deck operations |
| **Backend (modified)** | |
| `backend/app/models/schemas.py` | Add `DeckSummary`, `SaveDeckRequest`, `UpdateDeckRequest`, deck response models |
| `backend/app/dependencies.py` | Add `get_deck_store()` DI provider |
| `backend/app/main.py` | Register decks router, init DB on startup |
| `backend/app/routers/export.py` | Accept `deck_id` as alternative to `session_id` |
| `backend/app/config.py` | Add `deck_db_path` setting |
| **Backend (tests)** | |
| `backend/tests/test_deck_store.py` | Unit tests for DeckStore CRUD |
| `backend/tests/test_decks_api.py` | Integration tests for deck endpoints |
| `backend/tests/test_export_deck_id.py` | Test export with deck_id |
| **Frontend (new)** | |
| `frontend/src/pages/MyDecksPage.tsx` | Deck list with card grid, search/filter, delete |
| `frontend/src/pages/EditorPage.tsx` | Canvas editor with 3-panel layout |
| `frontend/src/lib/canvas-bridge.ts` | `renderSlideToCanvas()` and `exportCanvasToSlide()` |
| **Frontend (modified)** | |
| `frontend/src/lib/api.ts` | Add `listDecks`, `getDeck`, `saveDeck`, `updateDeck`, `deleteDeck` |
| `frontend/src/types/index.ts` | Add `DeckSummary`, `DeckDetail`, deck API types |
| `frontend/src/App.tsx` | Add `/my-decks` and `/editor/:deckId` routes |
| `frontend/src/pages/PreviewPage.tsx` | Add "Save to My Decks" button |
| **Frontend (tests)** | |
| `frontend/src/lib/canvas-bridge.test.ts` | Unit tests for canvas bridge functions |

---

### Task 1: Backend — Add deck DB path config

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add `deck_db_path` setting**

```python
# In Settings class, add after signed_url_expiry_minutes:
deck_db_path: str = ".data/decks.db"
```

Add this line in `backend/app/config.py` after line 20 (after `signed_url_expiry_minutes`):

```python
    deck_db_path: str = ".data/decks.db"
```

- [ ] **Step 2: Verify config loads**

Run: `cd backend && uv run python -c "from app.config import settings; print(settings.deck_db_path)"`
Expected: `.data/decks.db`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add deck_db_path config setting"
```

---

### Task 2: Backend — Add deck Pydantic schemas

**Files:**
- Modify: `backend/app/models/schemas.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_decks_schemas.py`:

```python
from app.models.schemas import DeckSummary, DeckDetail, SaveDeckRequest, UpdateDeckRequest

def test_deck_summary_excludes_full_slides():
    summary = DeckSummary(
        id="abc",
        name="Test Deck",
        deck_type="sales_9",
        slide_count=9,
        thumbnail_b64=None,
        created_at="2026-06-26T00:00:00Z",
        updated_at="2026-06-26T00:00:00Z",
    )
    data = summary.model_dump()
    assert "slides" not in data
    assert data["slide_count"] == 9

def test_save_deck_request_requires_name_and_slides():
    # Valid
    req = SaveDeckRequest(
        name="My Deck",
        deck_type="sales_9",
        theme="minimalist",
        aspect_ratio="16:9",
        slides=[],
    )
    assert req.name == "My Deck"

def test_update_deck_request_partial():
    req = UpdateDeckRequest(name="New Name")
    assert req.name == "New Name"
    assert req.slides is None

def test_deck_detail_includes_slides():
    detail = DeckDetail(
        id="abc",
        name="Test Deck",
        deck_type="sales_9",
        theme="minimalist",
        aspect_ratio="16:9",
        slides=[],
        thumbnail_b64=None,
        created_at="2026-06-26T00:00:00Z",
        updated_at="2026-06-26T00:00:00Z",
    )
    data = detail.model_dump()
    assert "slides" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_decks_schemas.py -v`
Expected: FAIL — all classes not defined

- [ ] **Step 3: Add models to schemas.py**

Add after `ExportResponse` (line 183) in `backend/app/models/schemas.py`:

```python
class DeckSummary(BaseModel):
    id: str
    name: str
    deck_type: str
    slide_count: int
    thumbnail_b64: str | None = None
    created_at: str
    updated_at: str


class DeckDetail(BaseModel):
    id: str
    name: str
    deck_type: str
    theme: str
    aspect_ratio: str
    slides: list[SlideData]
    thumbnail_b64: str | None = None
    created_at: str
    updated_at: str


class SaveDeckRequest(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    deck_type: str
    theme: str = "minimalist"
    aspect_ratio: str = "16:9"
    slides: list[SlideData]
    thumbnail_b64: str | None = None


class UpdateDeckRequest(BaseModel):
    name: str | None = Field(default=None, max_length=500)
    slides: list[SlideData] | None = None


class SaveDeckResponse(BaseModel):
    id: str
    name: str
    created_at: str


class UpdateDeckResponse(BaseModel):
    updated_at: str


class DeleteDeckResponse(BaseModel):
    ok: bool


class ListDecksResponse(BaseModel):
    decks: list[DeckSummary]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_decks_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/schemas.py backend/tests/test_decks_schemas.py
git commit -m "feat: add DeckSummary, DeckDetail, and deck request/response schemas"
```

---

### Task 3: Backend — Build DeckStore service

**Files:**
- Create: `backend/app/services/platform/deck_store.py`
- Create: `backend/tests/test_deck_store.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_deck_store.py`:

```python
import json
import os
import tempfile
from pathlib import Path

import pytest

from app.models.schemas import SlideData
from app.services.platform.deck_store import DeckStore


@pytest.fixture
def tmp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def sample_slides():
    return [
        SlideData(index=1, title="Cover", bullets=[], notes="", layout="title"),
        SlideData(index=2, title="Overview", bullets=["Bullet 1"], notes="Notes", layout="content"),
    ]


@pytest.mark.asyncio
async def test_create_and_get_deck(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    deck_id = await store.create(
        name="Test Deck",
        deck_type="sales_9",
        theme="minimalist",
        aspect_ratio="16:9",
        slides=sample_slides,
        thumbnail_b64=None,
    )
    assert deck_id
    assert len(deck_id) == 36  # UUID

    deck = await store.get(deck_id)
    assert deck is not None
    assert deck["name"] == "Test Deck"
    assert len(deck["slides"]) == 2


@pytest.mark.asyncio
async def test_list_decks(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    await store.create("Deck A", "sales_9", "minimalist", "16:9", sample_slides)
    await store.create("Deck B", "internal_6", "bold", "16:9", sample_slides)

    decks = await store.list_all()
    assert len(decks) == 2
    assert decks[0]["slide_count"] == 2
    assert "slides" not in decks[0]


@pytest.mark.asyncio
async def test_list_decks_with_search(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    await store.create("Revenue Pitch", "sales_9", "minimalist", "16:9", sample_slides)
    await store.create("Operations Review", "internal_6", "minimalist", "16:9", sample_slides)

    results = await store.list_all(search="Revenue")
    assert len(results) == 1
    assert results[0]["name"] == "Revenue Pitch"


@pytest.mark.asyncio
async def test_list_decks_with_type_filter(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    await store.create("Deck A", "sales_9", "minimalist", "16:9", sample_slides)
    await store.create("Deck B", "internal_6", "minimalist", "16:9", sample_slides)

    results = await store.list_all(deck_type="sales_9")
    assert len(results) == 1
    assert results[0]["deck_type"] == "sales_9"


@pytest.mark.asyncio
async def test_update_deck(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    deck_id = await store.create("Original", "sales_9", "minimalist", "16:9", sample_slides)

    success = await store.update(deck_id, name="Renamed")
    assert success

    deck = await store.get(deck_id)
    assert deck["name"] == "Renamed"


@pytest.mark.asyncio
async def test_delete_deck(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    deck_id = await store.create("To Delete", "sales_9", "minimalist", "16:9", sample_slides)
    assert await store.delete(deck_id)

    deck = await store.get(deck_id)
    assert deck is None


@pytest.mark.asyncio
async def test_get_nonexistent_deck(tmp_db_path):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    deck = await store.get("nonexistent-id")
    assert deck is None


@pytest.mark.asyncio
async def test_slides_serialization_roundtrip(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    deck_id = await store.create("Roundtrip", "sales_9", "minimalist", "16:9", sample_slides)
    deck = await store.get(deck_id)

    assert deck is not None
    restored = deck["slides"]
    assert len(restored) == 2
    assert isinstance(restored[0], SlideData)
    assert restored[0].title == "Cover"
    assert restored[1].title == "Overview"
    assert restored[1].bullets == ["Bullet 1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_deck_store.py -v`
Expected: FAIL — `DeckStore` not defined / `aiosqlite` not installed

- [ ] **Step 3: Install aiosqlite**

Run: `cd backend && uv add aiosqlite`

- [ ] **Step 4: Write DeckStore implementation**

Create `backend/app/services/platform/deck_store.py`:

```python
import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from app.models.schemas import SlideData


class DeckStore:
    def __init__(self, db_path: str):
        self._db_path = db_path

    async def initialize(self) -> None:
        import os
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS decks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    deck_type TEXT NOT NULL,
                    theme TEXT NOT NULL DEFAULT 'minimalist',
                    aspect_ratio TEXT NOT NULL DEFAULT '16:9',
                    slides TEXT NOT NULL DEFAULT '[]',
                    thumbnail_b64 TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await db.commit()

    async def create(
        self,
        name: str,
        deck_type: str,
        theme: str,
        aspect_ratio: str,
        slides: list[SlideData],
        thumbnail_b64: str | None = None,
    ) -> str:
        deck_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        slides_json = json.dumps([s.model_dump() for s in slides])
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO decks (id, name, deck_type, theme, aspect_ratio, slides, thumbnail_b64, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (deck_id, name, deck_type, theme, aspect_ratio, slides_json, thumbnail_b64, now, now),
            )
            await db.commit()
        return deck_id

    async def get(self, deck_id: str) -> dict | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    async def list_all(
        self,
        search: str = "",
        deck_type: str = "",
        sort: str = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        query = "SELECT id, name, deck_type, slides, thumbnail_b64, created_at, updated_at FROM decks"
        params: list = []
        conditions: list[str] = []

        if search:
            conditions.append("name LIKE ?")
            params.append(f"%{search}%")
        if deck_type:
            conditions.append("deck_type = ?")
            params.append(deck_type)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        if sort == "oldest":
            query += " ORDER BY created_at ASC"
        elif sort == "name":
            query += " ORDER BY name ASC"
        else:
            query += " ORDER BY created_at DESC"

        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()

        return [self._summary_from_row(r) for r in rows]

    async def update(
        self,
        deck_id: str,
        name: str | None = None,
        slides: list[SlideData] | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        updates: list[str] = ["updated_at = ?"]
        params: list = [now]

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if slides is not None:
            updates.append("slides = ?")
            params.append(json.dumps([s.model_dump() for s in slides]))

        params.append(deck_id)

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"UPDATE decks SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await db.commit()
        return cursor.rowcount > 0

    async def delete(self, deck_id: str) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
            await db.commit()
        return cursor.rowcount > 0

    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        d["slides"] = [SlideData(**s) for s in json.loads(d["slides"])]
        return d

    def _summary_from_row(self, row) -> dict:
        d = dict(row)
        slides = json.loads(d.pop("slides"))
        d["slide_count"] = len(slides)
        return d
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_deck_store.py -v`
Expected: PASS (all 8 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/platform/deck_store.py backend/tests/test_deck_store.py
git commit -m "feat: add DeckStore service with async SQLite CRUD"
```

---

### Task 4: Backend — Add DI provider for DeckStore

**Files:**
- Modify: `backend/app/dependencies.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add get_deck_store dependency**

Add to `backend/app/dependencies.py` after the existing imports and before `_audit_service`:

```python
from app.config import settings
from app.services.platform.deck_store import DeckStore
```

And add at the end of the file:

```python
_deck_store: DeckStore | None = None


def get_deck_store() -> DeckStore:
    global _deck_store
    if _deck_store is None:
        _deck_store = DeckStore(settings.deck_db_path)
    return _deck_store
```

- [ ] **Step 2: Initialize DB on startup**

In `backend/app/main.py`, add to the `lifespan` function, inside the `async with` block, before `yield`:

```python
    from app.dependencies import get_deck_store
    await get_deck_store().initialize()
```

Add after line 52 (`_validate_config()`):

```python
    from app.dependencies import get_deck_store
    await get_deck_store().initialize()
```

- [ ] **Step 3: Verify startup works**

Run: `cd backend && timeout 3 uv run uvicorn app.main:app 2>&1 || true`
Expected: No errors about deck_store / SQLite

- [ ] **Step 4: Commit**

```bash
git add backend/app/dependencies.py backend/app/main.py
git commit -m "feat: add DeckStore DI provider with startup initialization"
```

---

### Task 5: Backend — Build decks API router

**Files:**
- Create: `backend/app/routers/decks.py`
- Create: `backend/tests/test_decks_api.py`

- [ ] **Step 1: Write failing integration test**

Create `backend/tests/test_decks_api.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_save_and_list_decks(client: AsyncClient):
    slides = [
        {"index": 1, "title": "Cover", "bullets": [], "notes": "", "layout": "title"},
    ]
    save_resp = await client.post(
        "/api/v1/decks",
        json={
            "name": "API Test Deck",
            "deck_type": "sales_9",
            "theme": "minimalist",
            "aspect_ratio": "16:9",
            "slides": slides,
        },
    )
    assert save_resp.status_code == 200
    data = save_resp.json()
    assert "id" in data
    deck_id = data["id"]
    assert data["name"] == "API Test Deck"

    list_resp = await client.get("/api/v1/decks")
    assert list_resp.status_code == 200
    decks = list_resp.json()["decks"]
    assert len(decks) >= 1
    found = next((d for d in decks if d["id"] == deck_id), None)
    assert found is not None
    assert found["name"] == "API Test Deck"
    assert found["slide_count"] == 1


@pytest.mark.asyncio
async def test_get_deck_by_id(client: AsyncClient):
    slides = [
        {"index": 1, "title": "Cover", "bullets": [], "notes": "", "layout": "title"},
        {"index": 2, "title": "Overview", "bullets": ["Point A"], "notes": "N", "layout": "content"},
    ]
    save_resp = await client.post(
        "/api/v1/decks",
        json={
            "name": "Detail Test",
            "deck_type": "sales_9",
            "theme": "minimalist",
            "aspect_ratio": "16:9",
            "slides": slides,
        },
    )
    deck_id = save_resp.json()["id"]

    get_resp = await client.get(f"/api/v1/decks/{deck_id}")
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["name"] == "Detail Test"
    assert len(detail["slides"]) == 2
    assert detail["slides"][0]["title"] == "Cover"


@pytest.mark.asyncio
async def test_update_deck(client: AsyncClient):
    slides = [
        {"index": 1, "title": "Old", "bullets": [], "notes": "", "layout": "title"},
    ]
    save_resp = await client.post(
        "/api/v1/decks",
        json={
            "name": "Original",
            "deck_type": "sales_9",
            "theme": "minimalist",
            "aspect_ratio": "16:9",
            "slides": slides,
        },
    )
    deck_id = save_resp.json()["id"]

    new_slides = [
        {"index": 1, "title": "Renamed", "bullets": ["Updated bullet"], "notes": "", "layout": "title"},
    ]
    update_resp = await client.put(
        f"/api/v1/decks/{deck_id}",
        json={"name": "Renamed Deck", "slides": new_slides},
    )
    assert update_resp.status_code == 200
    assert "updated_at" in update_resp.json()

    get_resp = await client.get(f"/api/v1/decks/{deck_id}")
    detail = get_resp.json()
    assert detail["name"] == "Renamed Deck"
    assert detail["slides"][0]["title"] == "Renamed"


@pytest.mark.asyncio
async def test_delete_deck(client: AsyncClient):
    slides = [
        {"index": 1, "title": "Temp", "bullets": [], "notes": "", "layout": "title"},
    ]
    save_resp = await client.post(
        "/api/v1/decks",
        json={
            "name": "Delete Me",
            "deck_type": "sales_9",
            "theme": "minimalist",
            "aspect_ratio": "16:9",
            "slides": slides,
        },
    )
    deck_id = save_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/decks/{deck_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["ok"] is True

    get_resp = await client.get(f"/api/v1/decks/{deck_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_deck_404(client: AsyncClient):
    resp = await client.get("/api/v1/decks/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_decks_with_search(client: AsyncClient):
    slides = [
        {"index": 1, "title": "X", "bullets": [], "notes": "", "layout": "title"},
    ]
    await client.post(
        "/api/v1/decks",
        json={"name": "Alpha Deck", "deck_type": "sales_9", "theme": "minimalist", "aspect_ratio": "16:9", "slides": slides},
    )
    await client.post(
        "/api/v1/decks",
        json={"name": "Beta Deck", "deck_type": "sales_9", "theme": "minimalist", "aspect_ratio": "16:9", "slides": slides},
    )

    resp = await client.get("/api/v1/decks?q=Alpha")
    assert resp.status_code == 200
    decks = resp.json()["decks"]
    assert len(decks) == 1
    assert decks[0]["name"] == "Alpha Deck"


@pytest.mark.asyncio
async def test_save_deck_empty_name_returns_422(client: AsyncClient):
    resp = await client.post(
        "/api/v1/decks",
        json={"name": "", "deck_type": "sales_9", "theme": "minimalist", "aspect_ratio": "16:9", "slides": []},
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_decks_api.py -v`
Expected: FAIL — 404 on all deck routes (not registered yet)

- [ ] **Step 3: Create the decks router**

Create `backend/app/routers/decks.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_deck_store
from app.models.schemas import (
    DeckDetail,
    DeckSummary,
    DeleteDeckResponse,
    ListDecksResponse,
    SaveDeckRequest,
    SaveDeckResponse,
    UpdateDeckRequest,
    UpdateDeckResponse,
)
from app.services.platform.deck_store import DeckStore

router = APIRouter()


@router.get("/decks", response_model=ListDecksResponse)
async def list_decks(
    q: str = Query(default="", max_length=200),
    deck_type: str = Query(default=""),
    sort: str = Query(default="newest", pattern="^(newest|oldest|name)$"),
    store: DeckStore = Depends(get_deck_store),
):
    rows = await store.list_all(search=q, deck_type=deck_type, sort=sort)
    summaries = [DeckSummary(**r) for r in rows]
    return ListDecksResponse(decks=summaries)


@router.get("/decks/{deck_id}", response_model=DeckDetail)
async def get_deck(
    deck_id: str,
    store: DeckStore = Depends(get_deck_store),
):
    deck = await store.get(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return DeckDetail(**deck)


@router.post("/decks", response_model=SaveDeckResponse, status_code=200)
async def save_deck(
    req: SaveDeckRequest,
    store: DeckStore = Depends(get_deck_store),
):
    deck_id = await store.create(
        name=req.name,
        deck_type=req.deck_type,
        theme=req.theme,
        aspect_ratio=req.aspect_ratio,
        slides=req.slides,
        thumbnail_b64=req.thumbnail_b64,
    )
    deck = await store.get(deck_id)
    return SaveDeckResponse(
        id=deck_id,
        name=req.name,
        created_at=deck["created_at"] if deck else "",
    )


@router.put("/decks/{deck_id}", response_model=UpdateDeckResponse)
async def update_deck(
    deck_id: str,
    req: UpdateDeckRequest,
    store: DeckStore = Depends(get_deck_store),
):
    if req.name is None and req.slides is None:
        raise HTTPException(status_code=400, detail="At least one of name or slides must be provided")

    success = await store.update(
        deck_id=deck_id,
        name=req.name,
        slides=req.slides,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Deck not found")

    deck = await store.get(deck_id)
    return UpdateDeckResponse(
        updated_at=deck["updated_at"] if deck else "",
    )


@router.delete("/decks/{deck_id}", response_model=DeleteDeckResponse)
async def delete_deck(
    deck_id: str,
    store: DeckStore = Depends(get_deck_store),
):
    success = await store.delete(deck_id)
    if not success:
        raise HTTPException(status_code=404, detail="Deck not found")
    return DeleteDeckResponse(ok=True)
```

- [ ] **Step 4: Register router in main.py**

Add to imports in `backend/app/main.py` (before the `app.include_router` lines):

```python
from app.routers import decks
```

And add after the other `app.include_router` lines:

```python
app.include_router(decks.router, prefix="/api/v1", tags=["decks"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_decks_api.py -v`
Expected: PASS (all 7 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/decks.py backend/tests/test_decks_api.py backend/app/main.py
git commit -m "feat: add decks CRUD API router with 5 endpoints"
```

---

### Task 6: Backend — Extend export to support deck_id

**Files:**
- Modify: `backend/app/models/schemas.py` — update `ExportRequest`
- Modify: `backend/app/routers/export.py`
- Create: `backend/tests/test_export_deck_id.py`

- [ ] **Step 1: Update ExportRequest to accept optional deck_id**

In `backend/app/models/schemas.py`, replace `ExportRequest` (line 177-178):

```python
class ExportRequest(BaseModel):
    session_id: str | None = None
    deck_id: str | None = None
```

- [ ] **Step 2: Write failing test for deck_id export**

Create `backend/tests/test_export_deck_id.py`:

```python
from io import BytesIO

from httpx import AsyncClient, ASGITransport
from pptx import Presentation
import pytest

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_by_deck_id(client: AsyncClient):
    slides = [
        {"index": 1, "title": "Cover", "bullets": [], "notes": "", "layout": "title"},
        {"index": 2, "title": "Content", "bullets": ["Point"], "notes": "N", "layout": "content"},
    ]
    save_resp = await client.post(
        "/api/v1/decks",
        json={"name": "Export Deck", "deck_type": "sales_9", "theme": "minimalist", "aspect_ratio": "16:9", "slides": slides},
    )
    deck_id = save_resp.json()["id"]

    export_resp = await client.post("/api/v1/export", json={"deck_id": deck_id})
    assert export_resp.status_code == 200
    data = export_resp.json()
    assert data["download_url"].startswith("http://test/api/v1/download/")

    download = await client.get(data["download_url"].replace("http://test", ""))
    assert download.status_code == 200
    assert download.content.startswith(b"PK")
    prs = Presentation(BytesIO(download.content))
    assert len(prs.slides) >= 2


@pytest.mark.asyncio
async def test_export_no_session_or_deck_id_returns_422(client: AsyncClient):
    resp = await client.post("/api/v1/export", json={})
    assert resp.status_code == 422
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_export_deck_id.py -v`
Expected: FAIL — export doesn't handle deck_id yet

- [ ] **Step 4: Update export router**

Replace the `export_deck` function in `backend/app/routers/export.py` (lines 38-77) with:

```python
@router.post("/export")
@limiter.limit(settings.rate_limit_export)
async def export_deck(
    req: ExportRequest,
    request: Request,
    session_store: SessionStore = Depends(get_session_store),
    storage: StorageService = Depends(get_storage_service),
) -> ExportResponse:
    slides: list
    deck_type = "unknown"
    theme = "minimalist"
    aspect_ratio = "16:9"
    export_session_id = ""

    if req.deck_id:
        from app.dependencies import get_deck_store
        deck_store = get_deck_store()
        deck = await deck_store.get(req.deck_id)
        if deck is None:
            raise HTTPException(status_code=404, detail="Deck not found")
        slides = deck["slides"]
        deck_type = deck["deck_type"]
        theme = deck["theme"]
        aspect_ratio = deck["aspect_ratio"]
        export_session_id = req.deck_id
    elif req.session_id:
        session = session_store.get(req.session_id)
        if session is None:
            raise SessionNotFoundError(req.session_id)
        slides = session["slides"]
        deck_type = session.get("deck_type", "unknown")
        theme = session.get("theme", "minimalist")
        aspect_ratio = session.get("aspect_ratio", "16:9")
        export_session_id = req.session_id
    else:
        raise HTTPException(status_code=422, detail="Either session_id or deck_id is required")

    engine = PptxEngine(
        template_path=settings.sample_template_path,
        theme=theme,
        aspect_ratio=aspect_ratio,
    )
    max_count = SLIDE_COUNTS.get(deck_type, len(slides) + 1) + SLIDE_COUNT_TOLERANCE
    slides = normalize_deck(slides, max_count=max_count)
    pptx_bytes = engine.render(slides)
    try:
        _validate_pptx_bytes(pptx_bytes)
    except ValueError as exc:
        raise GenerationError(str(exc)) from exc

    url = await storage.upload_pptx(export_session_id, pptx_bytes, base_url=str(request.base_url))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.signed_url_expiry_minutes)
    audit = get_audit_service()
    audit.record(
        action="export",
        session_id=export_session_id,
        deck_type=deck_type,
        slide_count=len(slides),
        user_id=get_user_id(request),
        model=settings.gemini_model,
    )

    return ExportResponse(download_url=url, expires_at=expires_at)
```

Also update the import line to include `HTTPException`:

```python
from fastapi import APIRouter, Depends, HTTPException, Request
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_export_deck_id.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Verify existing tests still pass**

Run: `cd backend && uv run pytest tests/test_api.py -v -k export`
Expected: PASS (existing export tests)

- [ ] **Step 7: Run full backend test suite**

Run: `cd backend && uv run pytest -v`
Expected: All tests pass (20+ tests)

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/schemas.py backend/app/routers/export.py backend/tests/test_export_deck_id.py
git commit -m "feat: extend export to support deck_id as alternative to session_id"
```

---

### Task 7: Frontend — Add deck API types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add deck types**

Add at the end of `frontend/src/types/index.ts`:

```typescript
export interface DeckSummary {
  id: string
  name: string
  deck_type: DeckType
  slide_count: number
  thumbnail_b64: string | null
  created_at: string
  updated_at: string
}

export interface DeckDetail {
  id: string
  name: string
  deck_type: DeckType
  theme: string
  aspect_ratio: string
  slides: SlideData[]
  thumbnail_b64: string | null
  created_at: string
  updated_at: string
}

export interface SaveDeckRequest {
  name: string
  deck_type: DeckType
  theme: string
  aspect_ratio: string
  slides: SlideData[]
  thumbnail_b64?: string | null
}

export interface SaveDeckResponse {
  id: string
  name: string
  created_at: string
}

export interface UpdateDeckRequest {
  name?: string
  slides?: SlideData[]
}

export interface UpdateDeckResponse {
  updated_at: string
}

export interface ListDecksResponse {
  decks: DeckSummary[]
}
```

Also update `ExportRequest` to add `deck_id`:

```typescript
export interface ExportRequest {
  session_id?: string | null
  deck_id?: string | null
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add DeckSummary, DeckDetail, and deck API types"
```

---

### Task 8: Frontend — Add deck API functions

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add deck API functions**

Add to `frontend/src/lib/api.ts` after existing exports, also update the type imports:

Replace the import line:

```typescript
import type { GenerateRequest, GenerateResponse, RefineRequest, RefineResponse, ExportRequest, ExportResponse, UploadResponse } from '@/types'
```

With:

```typescript
import type {
  GenerateRequest, GenerateResponse,
  RefineRequest, RefineResponse,
  ExportRequest, ExportResponse,
  UploadResponse,
  ListDecksResponse, DeckDetail,
  SaveDeckRequest, SaveDeckResponse,
  UpdateDeckRequest, UpdateDeckResponse,
} from '@/types'
```

Add a new helper for GET requests, after the `parseError` function (after line 21):

```typescript
async function getRequest<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value) url.searchParams.set(key, value)
    }
  }
  const res = await fetch(url.toString())
  if (!res.ok) {
    throw await parseError(res)
  }
  return res.json()
}
```

Add at the end of the file:

```typescript
export function listDecks(params?: { q?: string; deck_type?: string; sort?: string }): Promise<ListDecksResponse> {
  return getRequest('/decks', params)
}

export function getDeck(deckId: string): Promise<DeckDetail> {
  return getRequest(`/decks/${deckId}`)
}

export function saveDeck(data: SaveDeckRequest): Promise<SaveDeckResponse> {
  return request('/decks', data)
}

export function updateDeck(deckId: string, data: UpdateDeckRequest): Promise<UpdateDeckResponse> {
  return fetch(`${BASE_URL}/decks/${deckId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(async (res) => {
    if (!res.ok) throw await parseError(res)
    return res.json()
  })
}

export async function deleteDeck(deckId: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE_URL}/decks/${deckId}`, { method: 'DELETE' })
  if (!res.ok) throw await parseError(res)
  return res.json()
}

export function exportDeckById(deckId: string): Promise<ExportResponse> {
  return request('/export', { deck_id: deckId })
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: add deck CRUD and export-by-id API functions"
```

---

### Task 9: Frontend — Build MyDecksPage

**Files:**
- Create: `frontend/src/pages/MyDecksPage.tsx`

- [ ] **Step 1: Write tests**

The frontend test file is `frontend/src/lib/canvas-bridge.test.ts` (will be created in Task 10). For MyDecksPage, we'll write component tests later. For now, we build the component.

- [ ] **Step 2: Create MyDecksPage component**

Create `frontend/src/pages/MyDecksPage.tsx`:

```typescript
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { listDecks, deleteDeck, exportDeckById } from '@/lib/api'
import type { DeckSummary } from '@/types'

const DECK_TYPE_LABELS: Record<string, string> = {
  sales_9: 'Sales Pitch',
  internal_6: 'Internal Update',
}

const DECK_TYPE_COLORS: Record<string, string> = {
  sales_9: 'from-citi-blue to-blue-900',
  internal_6: 'from-citi-red to-red-900',
}

const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'name', label: 'Name A-Z' },
]

export function MyDecksPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [deckTypeFilter, setDeckTypeFilter] = useState('')
  const [sort, setSort] = useState('newest')
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['decks', search, deckTypeFilter, sort],
    queryFn: () => listDecks({ q: search, deck_type: deckTypeFilter, sort }),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteDeck,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['decks'] })
      setDeleteConfirm(null)
    },
    onError: (err) => setError(err instanceof Error ? err.message : 'Failed to delete'),
  })

  const exportMutation = useMutation({
    mutationFn: exportDeckById,
    onSuccess: (data) => {
      window.open(data.download_url, '_blank')
    },
    onError: (err) => setError(err instanceof Error ? err.message : 'Failed to export'),
  })

  const decks = data?.decks ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-white">My Decks</h2>
          <p className="mt-1 text-slate-400">{decks.length} saved decks</p>
        </div>
        <Button variant="glow" onClick={() => navigate('/create')}>+ New Deck</Button>
      </div>

      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="Search decks..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[200px] rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-citi-blue"
        />
        <select
          value={deckTypeFilter}
          onChange={(e) => setDeckTypeFilter(e.target.value)}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        >
          <option value="">All Types</option>
          <option value="sales_9">Sales Pitch (9)</option>
          <option value="internal_6">Internal Update (6)</option>
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline">Dismiss</button>
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse rounded-xl border border-white/10 bg-white/5 h-48" />
          ))}
        </div>
      ) : decks.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="text-5xl mb-4">📭</div>
          <h3 className="text-xl font-semibold text-white">No decks yet</h3>
          <p className="mt-2 text-slate-400">Generate your first pitch deck to get started.</p>
          <Button variant="glow" className="mt-6" onClick={() => navigate('/create')}>
            Create your first deck
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {decks.map((deck: DeckSummary) => (
            <div key={deck.id} className="overflow-hidden rounded-xl border border-white/10 bg-white/5 transition hover:border-white/20">
              <div className={cn('h-28 flex items-center justify-center bg-gradient-to-br', DECK_TYPE_COLORS[deck.deck_type] || 'from-slate-700 to-slate-900')}>
                <div className="text-center">
                  <div className="text-2xl mb-1">{deck.deck_type === 'sales_9' ? '📊' : '📋'}</div>
                  <div className="text-xs text-white/70">{deck.slide_count} Slides</div>
                </div>
              </div>
              <div className="p-4">
                <div className="font-semibold text-white truncate">{deck.name}</div>
                <div className="text-xs text-slate-400 mt-0.5">
                  {DECK_TYPE_LABELS[deck.deck_type] || deck.deck_type} · {new Date(deck.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </div>
                <div className="flex gap-2 mt-3">
                  <Button size="sm" onClick={() => navigate(`/editor/${deck.id}`)}>Edit</Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-white/15 bg-white/5 text-slate-200 hover:border-indigo-400/50 hover:bg-white/10"
                    onClick={() => exportMutation.mutate(deck.id)}
                    disabled={exportMutation.isPending}
                  >
                    Export
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                    onClick={() => setDeleteConfirm(deck.id)}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="glass-card p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-semibold text-white">Delete this deck?</h3>
            <p className="mt-2 text-sm text-slate-400">This action cannot be undone.</p>
            <div className="flex gap-3 mt-4 justify-end">
              <Button variant="outline" className="border-white/15 bg-white/5 text-slate-200" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
              <Button
                variant="glow"
                className="bg-citi-red hover:bg-red-600"
                onClick={() => deleteMutation.mutate(deleteConfirm)}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Add route in App.tsx**

In `frontend/src/App.tsx`, add the import:

```typescript
import { MyDecksPage } from '@/pages/MyDecksPage'
```

And add the route inside the Layout group, before `/create`:

```typescript
<Route path="/my-decks" element={<MyDecksPage />} />
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: No type errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/MyDecksPage.tsx frontend/src/App.tsx
git commit -m "feat: add MyDecksPage with card grid, search, filter, delete"
```

---

### Task 10: Frontend — Build canvas bridge utility

**Files:**
- Create: `frontend/src/lib/canvas-bridge.ts`
- Create: `frontend/src/lib/canvas-bridge.test.ts`

- [ ] **Step 1: Install Fabric.js**

Run: `cd frontend && pnpm add fabric`

- [ ] **Step 2: Write tests**

Create `frontend/src/lib/canvas-bridge.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { createEmptySlide, slideToCanvasObjects, canvasObjectsToSlide } from './canvas-bridge'
import type { SlideData } from '@/types'

describe('createEmptySlide', () => {
  it('returns a minimal blank slide', () => {
    const slide = createEmptySlide(5)
    expect(slide.index).toBe(5)
    expect(slide.title).toBe('New Slide')
    expect(slide.bullets).toEqual([])
    expect(slide.layout).toBe('content')
    expect(slide.variant).toBeNull()
    expect(slide.notes).toBe('')
  })
})

describe('slideToCanvasObjects', () => {
  it('creates background rect', () => {
    const slide: SlideData = { index: 1, title: 'Test', bullets: [], notes: '', layout: 'content' }
    const objects = slideToCanvasObjects(slide, 960, 540, '#056DAE')
    expect(objects.length).toBeGreaterThanOrEqual(1)
    expect(objects[0]).toMatchObject({ type: 'rect', width: 960, height: 540, fill: '#056DAE' })
  })

  it('creates title textbox', () => {
    const slide: SlideData = { index: 1, title: 'Hello', bullets: [], notes: '', layout: 'content' }
    const objects = slideToCanvasObjects(slide, 960, 540, '#056DAE')
    const title = objects.find((o: any) => o.type === 'text' && o.text === 'Hello')
    expect(title).toBeDefined()
  })

  it('creates bullet textboxes with prefix', () => {
    const slide: SlideData = { index: 1, title: 'X', bullets: ['Point A', 'Point B'], notes: '', layout: 'content' }
    const objects = slideToCanvasObjects(slide, 960, 540, '#056DAE')
    const bullets = objects.filter((o: any) => o.type === 'text' && o.text?.startsWith('• '))
    expect(bullets).toHaveLength(2)
    expect(bullets[0].text).toBe('• Point A')
    expect(bullets[1].text).toBe('• Point B')
  })

  it('creates kicker textbox when present', () => {
    const slide: SlideData = { index: 1, title: 'X', kicker: 'SECTION A', bullets: [], notes: '', layout: 'content' }
    const objects = slideToCanvasObjects(slide, 960, 540, '#056DAE')
    const kicker = objects.find((o: any) => o.type === 'text' && o.text === 'SECTION A')
    expect(kicker).toBeDefined()
  })
})

describe('canvasObjectsToSlide', () => {
  it('extracts title from canvas objects', () => {
    const objects = [
      { type: 'rect', left: 0, top: 0 },
      { type: 'text', text: 'My Title', left: 60, top: 80, fontSize: 32, fontFamily: 'Inter', fontWeight: 'bold' },
    ]
    const result = canvasObjectsToSlide(objects, { index: 1, title: '', bullets: [], notes: '', layout: 'content' })
    expect(result.title).toBe('My Title')
  })

  it('extracts bullets from content area', () => {
    const objects = [
      { type: 'rect', left: 0, top: 0 },
      { type: 'text', text: 'Title', left: 60, top: 80 },
      { type: 'text', text: '• Bullet 1', left: 60, top: 220 },
      { type: 'text', text: '• Bullet 2', left: 60, top: 260 },
    ]
    const result = canvasObjectsToSlide(objects, { index: 1, title: '', bullets: [], notes: '', layout: 'content' })
    expect(result.bullets).toEqual(['Bullet 1', 'Bullet 2'])
  })

  it('extracts kicker from top area', () => {
    const objects = [
      { type: 'rect', left: 0, top: 0 },
      { type: 'text', text: 'KICKER', left: 60, top: 40, fontSize: 12 },
      { type: 'text', text: 'Title', left: 60, top: 80 },
    ]
    const result = canvasObjectsToSlide(objects, { index: 1, title: '', bullets: [], notes: '', layout: 'content' })
    expect(result.kicker).toBe('KICKER')
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && pnpm test -- --run src/lib/canvas-bridge.test.ts`
Expected: FAIL — module not found

- [ ] **Step 4: Implement canvas bridge**

Create `frontend/src/lib/canvas-bridge.ts`:

```typescript
import type { SlideData } from '@/types'

interface CanvasObject {
  type: string
  text?: string
  left?: number
  top?: number
  width?: number
  height?: number
  fontSize?: number
  fontFamily?: string
  fontWeight?: string | number
  fill?: string
  [key: string]: unknown
}

const CANVAS_W = 960
const CANVAS_H = 540

const TITLE_TOP = 80
const KICKER_TOP = 40
const BULLETS_START_TOP = 220
const BULLET_LINE_HEIGHT = 40

export function createEmptySlide(index: number): SlideData {
  return {
    index,
    title: 'New Slide',
    bullets: [],
    notes: '',
    layout: 'content',
    variant: null,
  }
}

export function slideToCanvasObjects(
  slide: SlideData,
  width: number = CANVAS_W,
  height: number = CANVAS_H,
  bgColor: string = '#1E293B',
): CanvasObject[] {
  const objects: CanvasObject[] = []

  objects.push({
    type: 'rect',
    left: 0,
    top: 0,
    width,
    height,
    fill: bgColor,
    selectable: false,
    evented: false,
  })

  if (slide.kicker) {
    objects.push({
      type: 'text',
      text: slide.kicker,
      left: 60,
      top: KICKER_TOP,
      fontSize: 14,
      fontFamily: 'Inter',
      fontWeight: '700',
      fill: '#E31837',
    })
  }

  objects.push({
    type: 'text',
    text: slide.title,
    left: 60,
    top: slide.kicker ? TITLE_TOP + 30 : KICKER_TOP + 20,
    fontSize: 32,
    fontFamily: 'Inter',
    fontWeight: 'bold',
    fill: '#FFFFFF',
  })

  if (slide.subtitle) {
    const titleObj = objects[objects.length - 1]
    const titleBottom = (titleObj.top as number) + 48
    objects.push({
      type: 'text',
      text: slide.subtitle,
      left: 60,
      top: titleBottom + 10,
      fontSize: 16,
      fontFamily: 'Inter',
      fill: '#94A3B8',
    })
  }

  const subtitleBottom = slide.subtitle ? ((objects[objects.length - 1].top as number) + 28) : 0
  let contentTop = Math.max(BULLETS_START_TOP, subtitleBottom + 20)

  if (slide.callout) {
    objects.push({
      type: 'rect',
      left: 60,
      top: contentTop,
      width: width - 120,
      height: 36,
      fill: 'rgba(5,109,174,0.15)',
      rx: 4,
      ry: 4,
      selectable: false,
    })
    objects.push({
      type: 'text',
      text: slide.callout,
      left: 72,
      top: contentTop + 8,
      fontSize: 14,
      fontFamily: 'Inter',
      fontStyle: 'italic',
      fill: '#056DAE',
    })
    contentTop += 50
  }

  slide.bullets.forEach((bullet, i) => {
    objects.push({
      type: 'text',
      text: `• ${bullet}`,
      left: 60,
      top: contentTop + i * BULLET_LINE_HEIGHT,
      fontSize: 14,
      fontFamily: 'Inter',
      fill: '#CBD5E1',
      width: width - 120,
    })
  })

  return objects
}

export function canvasObjectsToSlide(
  objects: CanvasObject[],
  originalSlide: SlideData,
): SlideData {
  const texts = objects
    .filter((o) => o.type === 'text' && o.text !== undefined)
    .sort((a, b) => (a.top ?? 0) - (b.top ?? 0))

  const result: SlideData = { ...originalSlide }

  const filtered = texts.filter((t) => t.text !== undefined)

  const kicker = filtered.find((t) => (t.top ?? 0) <= KICKER_TOP + 10)
  if (kicker) {
    result.kicker = kicker.text
  }

  const titleCandidates = filtered.filter((t) => (t.top ?? 0) > KICKER_TOP + 10 && (t.top ?? 0) <= TITLE_TOP + 60)
  if (titleCandidates.length > 0) {
    result.title = titleCandidates[0].text!
  }

  const potentiallySubtitle = filtered.filter((t) => (t.top ?? 0) > TITLE_TOP + 30 && (t.top ?? 0) < BULLETS_START_TOP)
  if (potentiallySubtitle.length > 0) {
    result.subtitle = potentiallySubtitle[0].text
  }

  const bullets = filtered
    .filter((t) => (t.top ?? 0) >= BULLETS_START_TOP - 10)
    .filter((t) => t.text!.startsWith('• '))
    .map((t) => t.text!.replace(/^• /, ''))

  result.bullets = bullets
  return result
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && pnpm test -- --run src/lib/canvas-bridge.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/canvas-bridge.ts frontend/src/lib/canvas-bridge.test.ts
git commit -m "feat: add canvas-bridge utility for SlideData <-> Fabric.js mapping"
```

---

### Task 11: Frontend — Build EditorPage with Fabric.js canvas

**Files:**
- Create: `frontend/src/pages/EditorPage.tsx`

- [ ] **Step 1: Create EditorPage component**

Create `frontend/src/pages/EditorPage.tsx`:

```typescript
import { useRef, useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as fabric from 'fabric'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { getDeck, updateDeck, exportDeckById, deleteDeck } from '@/lib/api'
import { slideToCanvasObjects, canvasObjectsToSlide, createEmptySlide } from '@/lib/canvas-bridge'
import type { SlideData, DeckDetail } from '@/types'

export function EditorPage() {
  const { deckId } = useParams<{ deckId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const fabricRef = useRef<fabric.Canvas | null>(null)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [deckName, setDeckName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isDirty, setIsDirty] = useState(false)
  const [zoom, setZoom] = useState(1)
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { data: deck, isLoading } = useQuery({
    queryKey: ['deck', deckId],
    queryFn: () => getDeck(deckId!),
    enabled: !!deckId,
  })

  const saveMutation = useMutation({
    mutationFn: (data: { slides: SlideData[]; name?: string }) =>
      updateDeck(deckId!, { slides: data.slides, name: data.name }),
    onSuccess: () => setIsDirty(false),
    onError: (err) => setError(err instanceof Error ? err.message : 'Failed to save'),
  })

  const exportMutation = useMutation({
    mutationFn: () => exportDeckById(deckId!),
    onSuccess: (data) => window.open(data.download_url, '_blank'),
  })

  const saveSlides = useCallback((slides: SlideData[]) => {
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    autoSaveTimer.current = setTimeout(() => {
      saveMutation.mutate({ slides })
    }, 3000)
    setIsDirty(true)
    saveMutation.mutate({ slides })
  }, [saveMutation])

  const renderSlide = useCallback((canvas: fabric.Canvas, slide: SlideData) => {
    canvas.clear()
    const objects = slideToCanvasObjects(slide, 960, 540, '#1E293B')

    for (const obj of objects) {
      if (obj.type === 'rect') {
        const rect = new fabric.Rect({
          left: obj.left || 0,
          top: obj.top || 0,
          width: obj.width || 960,
          height: obj.height || 540,
          fill: obj.fill || '#1E293B',
          selectable: obj.selectable !== false,
          evented: obj.evented !== false,
        })
        canvas.add(rect)
      } else if (obj.type === 'text') {
        const textbox = new fabric.Textbox(obj.text || '', {
          left: obj.left || 0,
          top: obj.top || 0,
          fontSize: obj.fontSize || 16,
          fontFamily: obj.fontFamily || 'Inter',
          fontWeight: Array.isArray(obj.fontWeight) ? obj.fontWeight[0] : obj.fontWeight || 'normal',
          fill: obj.fill || '#FFFFFF',
          width: (obj.width || 840) as number,
          editable: true,
        })
        canvas.add(textbox)
      }
    }
    canvas.renderAll()
    canvas.fire('object:modified')
  }, [])

  useEffect(() => {
    if (!canvasRef.current || !deck) return

    if (fabricRef.current) {
      fabricRef.current.dispose()
    }

    const canvas = new fabric.Canvas(canvasRef.current, {
      width: 960,
      height: 540,
      backgroundColor: '#0F172A',
      selection: true,
    })

    fabricRef.current = canvas

    canvas.on('object:modified', () => {
      if (!deck) return
      const currentSlide = deck.slides[selectedIndex]
      if (!currentSlide) return
      const objects = canvas.getObjects().map((o) => o.toJSON())
      const updated = canvasObjectsToSlide(objects as any[], currentSlide)
      const newSlides = [...deck.slides]
      newSlides[selectedIndex] = updated
      saveSlides(newSlides)
    })

    if (deck.slides[selectedIndex]) {
      renderSlide(canvas, deck.slides[selectedIndex])
    }

    const resizeCanvas = () => {
      if (!canvasRef.current?.parentElement) return
      const parent = canvasRef.current.parentElement
      const scale = Math.min(
        (parent.clientWidth - 40) / 960,
        (parent.clientHeight - 40) / 540,
      )
      canvas.setZoom(scale)
      canvas.setWidth(960 * scale)
      canvas.setHeight(540 * scale)
      setZoom(Math.round(scale * 100))
    }
    resizeCanvas()
    window.addEventListener('resize', resizeCanvas)

    return () => {
      window.removeEventListener('resize', resizeCanvas)
      canvas.dispose()
      fabricRef.current = null
    }
  }, [deck, selectedIndex, renderSlide, saveSlides])

  useEffect(() => {
    if (deck) setDeckName(deck.name)
  }, [deck])

  if (!deckId) return <div className="text-white p-8">No deck ID provided</div>

  if (isLoading) {
    return <div className="flex items-center justify-center py-20"><div className="animate-pulse text-white text-lg">Loading deck...</div></div>
  }

  if (!deck) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <h2 className="text-xl text-white">Deck not found</h2>
        <Button variant="glow" className="mt-4" onClick={() => navigate('/my-decks')}>Back to My Decks</Button>
      </div>
    )
  }

  const currentSlide = deck.slides[selectedIndex] || deck.slides[0]

  const handleSelectSlide = (index: number) => {
    if (fabricRef.current && deck) {
      const objects = fabricRef.current.getObjects().map((o) => o.toJSON())
      const updated = canvasObjectsToSlide(objects as any[], deck.slides[selectedIndex])
      const newSlides = [...deck.slides]
      newSlides[selectedIndex] = updated
      saveSlides(newSlides)
    }
    setSelectedIndex(index)
  }

  const handleAddSlide = () => {
    const newSlide = createEmptySlide(deck.slides.length + 1)
    const newSlides = [...deck.slides, newSlide]
    saveMutation.mutate({ slides: newSlides })
    queryClient.setQueryData(['deck', deckId], { ...deck, slides: newSlides })
    setSelectedIndex(newSlides.length - 1)
  }

  const handleDeleteSlide = (index: number) => {
    if (deck.slides.length <= 1) return
    const newSlides = deck.slides.filter((_, i) => i !== index).map((s, i) => ({ ...s, index: i + 1 }))
    saveMutation.mutate({ slides: newSlides })
    queryClient.setQueryData(['deck', deckId], { ...deck, slides: newSlides })
    setSelectedIndex(Math.min(index, newSlides.length - 1))
  }

  const handleSaveName = () => {
    if (deckName !== deck.name) {
      saveMutation.mutate({ slides: deck.slides, name: deckName })
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] -mx-4 sm:-mx-6 lg:-mx-8 -mb-6">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-citi-dark border-b border-white/10 shrink-0">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/my-decks')} className="text-slate-400 hover:text-white text-sm">← Back</button>
          <input
            type="text"
            value={deckName}
            onChange={(e) => setDeckName(e.target.value)}
            onBlur={handleSaveName}
            onKeyDown={(e) => e.key === 'Enter' && handleSaveName()}
            className="bg-transparent text-white font-semibold text-sm border-none outline-none focus:ring-1 focus:ring-citi-blue rounded px-2 py-0.5"
          />
          <span className="text-xs text-slate-500">Slide {selectedIndex + 1} of {deck.slides.length}</span>
          {isDirty && <span className="text-xs text-yellow-400">Unsaved changes</span>}
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="border-white/15 bg-white/5 text-slate-200" onClick={handleSaveName}>Save</Button>
          <Button size="sm" variant="glow" onClick={() => exportMutation.mutate()} disabled={exportMutation.isPending}>
            Export PPTX
          </Button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Left: Slide thumbs */}
        <div className="w-44 bg-citi-dark/50 border-r border-white/10 overflow-y-auto shrink-0">
          <div className="p-2">
            <div className="text-[10px] uppercase text-slate-500 font-semibold px-1 mb-2">Slides</div>
            {deck.slides.map((slide: SlideData, i: number) => (
              <button
                key={i}
                onClick={() => handleSelectSlide(i)}
                className={cn(
                  'w-full text-left p-2 rounded mb-1 text-xs transition',
                  selectedIndex === i
                    ? 'bg-citi-blue/20 border border-citi-blue/50 text-white'
                    : 'border border-transparent text-slate-400 hover:bg-white/5 hover:text-white',
                )}
              >
                <div className="font-medium truncate">{slide.title}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">{slide.bullets.length} bullets</div>
              </button>
            ))}
            <button
              onClick={handleAddSlide}
              className="w-full mt-2 py-1.5 rounded text-xs font-medium bg-citi-blue/20 text-citi-blue hover:bg-citi-blue/30 transition"
            >
              + Add Slide
            </button>
          </div>
        </div>

        {/* Center: Canvas */}
        <div className="flex-1 bg-slate-700 flex items-center justify-center relative overflow-hidden">
          <div className="absolute top-2 left-1/2 -translate-x-1/2 flex items-center gap-1 bg-slate-800 rounded-lg px-2 py-1 z-10">
            <button onClick={() => fabricRef.current?.setZoom((fabricRef.current.getZoom() || 1) * 0.8)} className="text-white text-xs px-1">−</button>
            <span className="text-white text-xs px-1">{zoom}%</span>
            <button onClick={() => fabricRef.current?.setZoom((fabricRef.current.getZoom() || 1) * 1.25)} className="text-white text-xs px-1">+</button>
          </div>
          <div className="shadow-2xl">
            <canvas ref={canvasRef} />
          </div>
        </div>

        {/* Right: Properties */}
        <div className="w-60 bg-citi-dark/50 border-l border-white/10 overflow-y-auto shrink-0 p-3">
          <div className="text-[10px] uppercase text-slate-500 font-semibold mb-3">Properties</div>

          {currentSlide && (
            <div className="space-y-3">
              <div>
                <label className="text-[10px] text-slate-500 block mb-1">Title</label>
                <input
                  type="text"
                  value={currentSlide.title}
                  onChange={(e) => {
                    const newSlides = deck.slides.map((s, i) =>
                      i === selectedIndex ? { ...s, title: e.target.value } : s,
                    )
                    queryClient.setQueryData(['deck', deckId], { ...deck, slides: newSlides })
                    saveMutation.mutate({ slides: newSlides })
                  }}
                  className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white"
                />
              </div>

              {currentSlide.kicker !== undefined && (
                <div>
                  <label className="text-[10px] text-slate-500 block mb-1">Kicker</label>
                  <input
                    type="text"
                    value={currentSlide.kicker || ''}
                    onChange={(e) => {
                      const newSlides = deck.slides.map((s, i) =>
                        i === selectedIndex ? { ...s, kicker: e.target.value || null } : s,
                      )
                      queryClient.setQueryData(['deck', deckId], { ...deck, slides: newSlides })
                      saveMutation.mutate({ slides: newSlides })
                    }}
                    className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white"
                  />
                </div>
              )}

              <div>
                <label className="text-[10px] text-slate-500 block mb-1">Layout</label>
                <select
                  value={currentSlide.layout}
                  onChange={(e) => {
                    const newSlides = deck.slides.map((s, i) =>
                      i === selectedIndex ? { ...s, layout: e.target.value } : s,
                    )
                    queryClient.setQueryData(['deck', deckId], { ...deck, slides: newSlides })
                    saveMutation.mutate({ slides: newSlides })
                  }}
                  className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white"
                >
                  <option value="title">Title</option>
                  <option value="content">Content</option>
                  <option value="chart">Chart</option>
                  <option value="next_steps">Next Steps</option>
                </select>
              </div>

              <div>
                <label className="text-[10px] text-slate-500 block mb-1">Bullet Points</label>
                <div className="space-y-1">
                  {currentSlide.bullets.map((b: string, bi: number) => (
                    <input
                      key={bi}
                      type="text"
                      value={b}
                      onChange={(e) => {
                        const newBullets = [...currentSlide.bullets]
                        newBullets[bi] = e.target.value
                        const newSlides = deck.slides.map((s, i) =>
                          i === selectedIndex ? { ...s, bullets: newBullets } : s,
                        )
                        queryClient.setQueryData(['deck', deckId], { ...deck, slides: newSlides })
                        saveMutation.mutate({ slides: newSlides })
                      }}
                      className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white"
                    />
                  ))}
                  <button
                    onClick={() => {
                      const newSlides = deck.slides.map((s, i) =>
                        i === selectedIndex ? { ...s, bullets: [...s.bullets, ''] } : s,
                      )
                      queryClient.setQueryData(['deck', deckId], { ...deck, slides: newSlides })
                      saveMutation.mutate({ slides: newSlides })
                    }}
                    className="text-[10px] text-citi-blue hover:underline"
                  >
                    + Add bullet
                  </button>
                </div>
              </div>

              <div>
                <label className="text-[10px] text-slate-500 block mb-1">Speaker Notes</label>
                <textarea
                  value={currentSlide.notes || ''}
                  onChange={(e) => {
                    const newSlides = deck.slides.map((s, i) =>
                      i === selectedIndex ? { ...s, notes: e.target.value || '' } : s,
                    )
                    queryClient.setQueryData(['deck', deckId], { ...deck, slides: newSlides })
                    saveMutation.mutate({ slides: newSlides })
                  }}
                  rows={5}
                  className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white resize-none"
                />
              </div>

              {deck.slides.length > 1 && (
                <button
                  onClick={() => handleDeleteSlide(selectedIndex)}
                  className="text-xs text-red-400 hover:text-red-300 mt-2"
                >
                  Delete this slide
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add route in App.tsx**

In `frontend/src/App.tsx`, add the import:

```typescript
import { EditorPage } from '@/pages/EditorPage'
```

And add the route inside the Layout group:

```typescript
<Route path="/editor/:deckId" element={<EditorPage />} />
```

New order in Layout:
```typescript
<Route element={<Layout />}>
  <Route path="/create" element={<CreatePage />} />
  <Route path="/preview" element={<PreviewPage />} />
  <Route path="/export" element={<ExportPage />} />
  <Route path="/my-decks" element={<MyDecksPage />} />
  <Route path="/editor/:deckId" element={<EditorPage />} />
</Route>
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: No type errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/EditorPage.tsx frontend/src/App.tsx
git commit -m "feat: add EditorPage with Fabric.js canvas and 3-panel layout"
```

---

### Task 12: Frontend — Add "Save to My Decks" button to PreviewPage

**Files:**
- Modify: `frontend/src/pages/PreviewPage.tsx`

- [ ] **Step 1: Add save button to PreviewPage**

In `frontend/src/pages/PreviewPage.tsx`, add to imports:

```typescript
import { saveDeck } from '@/lib/api'
```

And `useClipboard` is not needed, but we need a mutation for saving. Add after the `refineMutation` declaration:

```typescript
const saveMutation = useMutation({
  mutationFn: saveDeck,
  onSuccess: () => navigate('/my-decks'),
  onError: (err) => setError(err instanceof Error ? err.message : 'Failed to save deck'),
})
```

Add to imports needed at top — change the first import to include `useMutation`:

```typescript
import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
```

These are already imported. Just add the save button next to the "Export to PPTX" button in the header. Replace the existing header right side (line 48):

```typescript
<div className="flex gap-3">
  <Button
    variant="outline"
    className="border-white/15 bg-white/5 text-slate-200 hover:border-indigo-400/50 hover:bg-white/10"
    onClick={() => {
      saveMutation.mutate({
        name: state.slides[0]?.title || 'Untitled Deck',
        deck_type: state.deckType || 'sales_9',
        theme: 'minimalist',
        aspect_ratio: '16:9',
        slides: state.slides,
      })
    }}
    disabled={saveMutation.isPending}
  >
    {saveMutation.isPending ? 'Saving...' : 'Save to My Decks'}
  </Button>
  <Button variant="glow" onClick={() => navigate('/export')}>Export to PPTX</Button>
</div>
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/PreviewPage.tsx
git commit -m "feat: add Save to My Decks button on PreviewPage"
```

---

### Task 13: Final verification

- [ ] **Step 1: Run backend tests**

Run: `cd backend && uv run pytest -v`
Expected: All tests pass

- [ ] **Step 2: Run frontend lint and typecheck**

Run: `cd frontend && pnpm tsc -b && pnpm lint`
Expected: No errors

- [ ] **Step 3: Run frontend tests**

Run: `cd frontend && pnpm test -- --run`
Expected: All tests pass

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final verification fixes"
```

---

## Self-Review Checklist

- **Spec coverage:** Deck storage (Task 2,3), CRUD endpoints (Task 5), Export deck_id (Task 6), MyDecksPage (Task 9), EditorPage (Task 11), Canvas bridge (Task 10), Save from Preview (Task 12)
- **Placeholder scan:** No TBD/TODO/placeholders found
- **Type consistency:** `DeckSummary` used in both backend (Pydantic) and frontend (TypeScript). `SaveDeckRequest`/`UpdateDeckRequest` consistent across both. `canvasObjectsToSlide` signature matches usage in EditorPage.

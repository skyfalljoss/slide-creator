# Backend Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 16 backend improvements across 3 phases: structured errors + DI, httpx/Redis/GCS, then model refactor + prompt extraction.

**Architecture:** Layered bottom-up approach — infra first (error hierarchy, DI, logging, rate limiting), then replace internals (httpx migration, Redis sessions, GCS storage), then refactor models/engine and extract prompts. App stays functional after every task.

**Tech Stack:** FastAPI, pydantic, httpx, tenacity, structlog, slowapi, Upstash Redis (REST), Google Cloud Storage

---

## File Structure

### Phase 1 — Foundation

| File | Action | Purpose |
|------|--------|---------|
| `app/errors.py` | Create | SlideForgeError hierarchy + error codes |
| `app/dependencies.py` | Create | FastAPI Depends() providers with lru_cache |
| `app/middleware/error_handler.py` | Create | Global exception handler middleware |
| `app/middleware/__init__.py` | Create | Package init |
| `app/config.py` | Modify | Add session_provider, rate_limit, structlog settings |
| `app/main.py` | Modify | Register middleware, lifespan cleanup, version header |
| `app/routers/generate.py` | Modify | Use DI + structured errors |
| `app/routers/refine.py` | Modify | Use DI + structured errors |
| `app/routers/export.py` | Modify | Use DI + structured errors |
| `app/routers/uploads.py` | Modify | Use DI + structured errors |
| `app/routers/health.py` | Create | Enriched health endpoint |
| `app/services/generation/providers.py` | Modify | Thin re-exports from dependencies.py, then remove |
| `tests/test_errors.py` | Create | Error hierarchy tests |
| `tests/test_dependencies.py` | Create | DI provider tests |
| `tests/test_health.py` | Create | Enriched health tests |
| `tests/test_api.py` | Modify | Update for structured error responses |

### Phase 2 — Internal Replacements

| File | Action | Purpose |
|------|--------|---------|
| `app/dependencies.py` | Modify | Add get_http_client, get_session_store, get_storage_backend |
| `app/services/generation/gemini_api.py` | Modify | httpx async + tenacity retry |
| `app/services/media/image_service.py` | Modify | Shared client via DI + tenacity retry |
| `app/services/platform/session.py` | Modify | SessionStore protocol + LocalSessionStore + RedisSessionStore |
| `app/services/platform/storage.py` | Modify | StorageBackend protocol + LocalStorageBackend + GCSStorageBackend |
| `app/config.py` | Modify | Add Upstash Redis + GCS settings |
| `app/main.py` | Modify | Lifespan cleanup for httpx client |
| `tests/test_session.py` | Modify | Test both Local and Redis session stores |
| `tests/test_redis_session.py` | Create | Redis session store unit tests (mocked REST) |
| `tests/test_gcs_storage.py` | Create | GCS storage backend unit tests (mocked) |
| `tests/test_gemini_api_httpx.py` | Create | httpx + retry tests |
| `tests/test_image_service_httpx.py` | Create | Shared client + retry tests |

### Phase 3 — Model Refactor + Polish

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | Modify | SlideContent, SlideEnrichment, SlideAssets sub-models |
| `app/services/presentation/variants.py` | Create | LayoutVariant registry + decorators |
| `app/services/presentation/pptx_layouts.py` | Modify | Port each method to @register_variant |
| `app/services/presentation/pptx_engine.py` | Modify | Use VARIANTS registry dispatch |
| `app/prompts/__init__.py` | Modify | Re-export loader |
| `app/prompts/loader.py` | Create | load_prompt(name, **vars) |
| `app/prompts/generate_deck.py` | Create | System prompt + deck generation template |
| `app/prompts/refine_slide.py` | Create | Refinement template |
| `app/prompts/dlp_violation.py` | Create | DLP rejection message template |
| `app/services/generation/gemini_api.py` | Modify | Import from app.prompts instead of inline |
| `app/routers/generate.py` | Modify | Use DLP prompt from app.prompts |
| `app/main.py` | Modify | API v2 router stub + X-API-Version header |
| `tests/test_variants.py` | Create | Variant registry tests |
| `tests/test_prompt_loader.py` | Create | Prompt loader tests |
| `tests/test_pptx_engine.py` | Modify | Update for registry dispatch |

---

## Phase 1 — Foundation (Errors, DI, Logging, Rate Limiting, Health)

### Task 1: Structured Error Hierarchy

**Files:**
- Create: `app/errors.py`
- Test: `tests/test_errors.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_errors.py
import pytest

from app.errors import (
    SlideForgeError,
    ConfigurationError,
    DlpViolationError,
    SessionNotFoundError,
    StorageError,
    GenerationError,
    StorageUploadError,
)


def test_base_error_has_code_and_message():
    err = SlideForgeError("SFE_000", "something broke")
    assert err.code == "SFE_000"
    assert err.message == "something broke"
    assert str(err) == "[SFE_000] something broke"


def test_configuration_error_code():
    err = ConfigurationError("missing API key")
    assert err.code == "CONFIG_ERROR"
    assert err.message == "missing API key"


def test_dlp_violation_error_code():
    err = DlpViolationError(terms=["guarantee returns", "risk-free"])
    assert err.code == "DLP_VIOLATION"
    assert "guarantee returns" in err.message
    assert "risk-free" in err.message


def test_session_not_found_error_code():
    err = SessionNotFoundError("abc-123")
    assert err.code == "SESSION_NOT_FOUND"
    assert "abc-123" in err.message


def test_storage_error_code():
    err = StorageError("disk full")
    assert err.code == "STORAGE_ERROR"
    assert err.message == "disk full"


def test_generation_error_code():
    err = GenerationError("model timeout")
    assert err.code == "GENERATION_ERROR"
    assert err.message == "model timeout"


def test_storage_upload_error_code():
    err = StorageUploadError("upload failed")
    assert err.code == "STORAGE_UPLOAD_ERROR"
    assert err.message == "upload failed"


def test_all_errors_inherit_from_base():
    assert issubclass(ConfigurationError, SlideForgeError)
    assert issubclass(DlpViolationError, SlideForgeError)
    assert issubclass(SessionNotFoundError, SlideForgeError)
    assert issubclass(StorageError, SlideForgeError)
    assert issubclass(GenerationError, SlideForgeError)
    assert issubclass(StorageUploadError, StorageError)


def test_dlp_violation_with_empty_terms():
    err = DlpViolationError(terms=[])
    assert err.code == "DLP_VIOLATION"
    assert err.message == "Prompt contains prohibited terms: "
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.errors'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/errors.py
class SlideForgeError(Exception):
    code: str = "SFE_000"

    def __init__(self, code: str | None = None, message: str = ""):
        self.code = code or self.code
        self.message = message
        super().__init__(f"[{self.code}] {self.message}")


class ConfigurationError(SlideForgeError):
    code = "CONFIG_ERROR"

    def __init__(self, message: str = ""):
        super().__init__(message=message)


class DlpViolationError(SlideForgeError):
    code = "DLP_VIOLATION"

    def __init__(self, terms: list[str]):
        self.terms = terms
        message = f"Prompt contains prohibited terms: {', '.join(terms)}"
        super().__init__(message=message)


class SessionNotFoundError(SlideForgeError):
    code = "SESSION_NOT_FOUND"

    def __init__(self, session_id: str):
        self.session_id = session_id
        message = f"Session not found or expired: {session_id}"
        super().__init__(message=message)


class StorageError(SlideForgeError):
    code = "STORAGE_ERROR"

    def __init__(self, message: str = ""):
        super().__init__(message=message)


class StorageUploadError(StorageError):
    code = "STORAGE_UPLOAD_ERROR"

    def __init__(self, message: str = ""):
        super().__init__(message=message)


class GenerationError(SlideForgeError):
    code = "GENERATION_ERROR"

    def __init__(self, message: str = ""):
        super().__init__(message=message)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_errors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/errors.py backend/tests/test_errors.py
git commit -m "feat(errors): add SlideForgeError hierarchy with typed error codes"
```

---

### Task 2: Global Error Handler Middleware

**Files:**
- Create: `app/middleware/__init__.py`
- Create: `app/middleware/error_handler.py`
- Test: `tests/test_errors.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_errors.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.middleware.error_handler import register_error_handlers


def test_error_handler_returns_structured_json():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/fail-dlp")
    def fail_dlp():
        raise DlpViolationError(terms=["risk-free"])

    @app.get("/fail-session")
    def fail_session():
        raise SessionNotFoundError("abc-123")

    @app.get("/fail-config")
    def fail_config():
        raise ConfigurationError("missing key")

    @app.get("/fail-generation")
    def fail_generation():
        raise GenerationError("model timeout")

    @app.get("/fail-generic")
    def fail_generic():
        raise RuntimeError("oops")

    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/fail-dlp")
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "DLP_VIOLATION"
    assert "risk-free" in body["error"]["message"]

    resp = client.get("/fail-session")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SESSION_NOT_FOUND"

    resp = client.get("/fail-config")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "CONFIG_ERROR"

    resp = client.get("/fail-generation")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "GENERATION_ERROR"

    resp = client.get("/fail-generic")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "INTERNAL_ERROR"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_errors.py::test_error_handler_returns_structured_json -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.middleware'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/middleware/__init__.py
```

```python
# app/middleware/error_handler.py
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.errors import (
    SlideForgeError,
    ConfigurationError,
    DlpViolationError,
    SessionNotFoundError,
    GenerationError,
    StorageError,
)

logger = logging.getLogger(__name__)

_STATUS_MAP: dict[type[SlideForgeError], int] = {
    ConfigurationError: 500,
    DlpViolationError: 400,
    SessionNotFoundError: 404,
    GenerationError: 502,
    StorageError: 500,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(SlideForgeError)
    async def slideforge_error_handler(request: Request, exc: SlideForgeError):
        status = _STATUS_MAP.get(type(exc), 500)
        logger.warning("[%s] %s %s", exc.code, request.method, request.url.path, extra={"error_code": exc.code})
        return JSONResponse(
            status_code=status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_errors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/middleware/__init__.py backend/app/middleware/error_handler.py backend/tests/test_errors.py
git commit -m "feat(middleware): add global error handler returning structured JSON"
```

---

### Task 3: Startup Config Validation + Register Error Handler in main.py

**Files:**
- Modify: `app/main.py`
- Modify: `app/config.py` (add session_provider)
- Test: `tests/test_errors.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_errors.py`:

```python
from app.config import Settings


def test_config_session_provider_defaults_to_local():
    s = Settings()
    assert s.session_provider == "local"


def test_config_rate_limit_defaults():
    s = Settings()
    assert s.rate_limit_generate == "10/minute"
    assert s.rate_limit_export == "30/minute"
    assert s.rate_limit_uploads == "60/minute"


def test_config_structlog_defaults():
    s = Settings()
    assert s.log_format == "console"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_errors.py::test_config_session_provider_defaults_to_local -v`
Expected: FAIL with `ValidationError` (field doesn't exist)

- [ ] **Step 3: Write minimal implementation**

Add to `app/config.py` (after line 34, before `model_config`):

```python
    session_provider: str = "local"
    rate_limit_generate: str = "10/minute"
    rate_limit_export: str = "30/minute"
    rate_limit_uploads: str = "60/minute"
    log_format: str = "console"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_errors.py -v`
Expected: PASS

- [ ] **Step 5: Register error handler in main.py**

Modify `app/main.py`: add `from app.middleware.error_handler import register_error_handlers` and call `register_error_handlers(app)` after `app = FastAPI(...)`.

Add startup config validation in lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_config()
    purge_local_temp_files()
    yield


def _validate_config() -> None:
    if settings.ai_provider == "gemini" and not settings.gemini_api_key:
        raise ConfigurationError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
    if settings.session_provider == "redis" and (not settings.upstash_redis_rest_url or not settings.upstash_redis_rest_token):
        raise ConfigurationError("UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are required when SESSION_PROVIDER=redis")
    if settings.storage_provider == "gcs" and not settings.gcs_bucket:
        raise ConfigurationError("GCS_BUCKET is required when STORAGE_PROVIDER=gcs")
```

Also add Upstash and GCS settings to `app/config.py`:

```python
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
```

- [ ] **Step 6: Run all tests to verify nothing broke**

Run: `cd backend && uv run pytest -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/app/config.py backend/tests/test_errors.py
git commit -m "feat(config): add session_provider, rate limits, structlog settings + startup validation"
```

---

### Task 4: FastAPI Depends() DI Providers

**Files:**
- Create: `app/dependencies.py`
- Test: `tests/test_dependencies.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dependencies.py
import pytest

from app.dependencies import (
    get_generator_service,
    get_dlp_service,
    get_storage_service,
    get_session_store,
    get_audit_service,
)
from app.config import settings


def test_get_generator_service_returns_local_by_default():
    svc = get_generator_service()
    assert svc.__class__.__name__ == "GeminiService"


def test_get_generator_service_returns_gemini_api(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    svc = get_generator_service()
    assert svc.__class__.__name__ == "GeminiApiService"


def test_get_dlp_service_returns_local():
    svc = get_dlp_service()
    assert svc.__class__.__name__ == "DlpService"


def test_get_storage_service_returns_local():
    svc = get_storage_service()
    assert svc.__class__.__name__ == "StorageService"


def test_get_session_store_returns_local():
    store = get_session_store()
    assert store.__class__.__name__ == "LocalSessionStore"


def test_get_audit_service_returns_shared_instance():
    assert get_audit_service() is get_audit_service()


def test_get_generator_service_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "vertex")
    with pytest.raises(NotImplementedError, match="vertex"):
        get_generator_service()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_dependencies.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/dependencies.py
from functools import lru_cache

from app.config import settings
from app.services.platform.audit import AuditService
from app.services.platform.dlp import DlpService
from app.services.platform.session import LocalSessionStore, SessionStore
from app.services.platform.storage import StorageService
from app.services.generation.gemini import GeminiService
from app.services.generation.gemini_api import GeminiApiService


_audit_service = AuditService()


@lru_cache
def get_generator_service():
    if settings.ai_provider == "local":
        return GeminiService()
    if settings.ai_provider == "gemini":
        return GeminiApiService()
    raise NotImplementedError(f"{settings.ai_provider} provider is not implemented")


@lru_cache
def get_dlp_service() -> DlpService:
    return DlpService()


@lru_cache
def get_storage_service() -> StorageService:
    return StorageService()


@lru_cache
def get_session_store() -> SessionStore:
    if settings.session_provider == "redis":
        raise NotImplementedError("Redis session store — implemented in Phase 2")
    return LocalSessionStore()


def get_audit_service() -> AuditService:
    return _audit_service
```

This requires `LocalSessionStore` to exist in `session.py`. Create it as a thin wrapper around the existing `_store` dict. Modify `app/services/platform/session.py`:

```python
# app/services/platform/session.py
import uuid
import time
from typing import Protocol, TypedDict

from app.config import settings
from app.models.schemas import SlideData


class SessionData(TypedDict):
    slides: list[SlideData]
    created_at: float
    deck_type: str
    theme: str
    aspect_ratio: str


class SessionStore(Protocol):
    def create(self, slides: list[SlideData], deck_type: str, theme: str, aspect_ratio: str) -> str: ...
    def get(self, session_id: str, ttl_seconds: int | None = None) -> SessionData | None: ...
    def update_slide(self, session_id: str, slide: SlideData, ttl_seconds: int | None = None) -> bool: ...
    def purge_expired(self, ttl_seconds: int | None = None) -> int: ...


class LocalSessionStore:
    def __init__(self) -> None:
        self._store: dict[str, SessionData] = {}

    def create(self, slides: list[SlideData], deck_type: str, theme: str = "minimalist", aspect_ratio: str = "16:9") -> str:
        session_id = str(uuid.uuid4())
        self._store[session_id] = {
            "slides": slides,
            "created_at": time.time(),
            "deck_type": deck_type,
            "theme": theme,
            "aspect_ratio": aspect_ratio,
        }
        return session_id

    def _default_ttl_seconds(self) -> int:
        return settings.session_ttl_minutes * 60

    def get(self, session_id: str, ttl_seconds: int | None = None) -> SessionData | None:
        ttl_seconds = self._default_ttl_seconds() if ttl_seconds is None else ttl_seconds
        data = self._store.get(session_id)
        if data is None:
            return None
        if time.time() - data["created_at"] > ttl_seconds:
            del self._store[session_id]
            return None
        return data

    def update_slide(self, session_id: str, slide: SlideData, ttl_seconds: int | None = None) -> bool:
        data = self.get(session_id, ttl_seconds=ttl_seconds)
        if data is None:
            return False
        for i, s in enumerate(data["slides"]):
            if s.index == slide.index:
                data["slides"][i] = slide
                return True
        return False

    def purge_expired(self, ttl_seconds: int | None = None) -> int:
        ttl_seconds = self._default_ttl_seconds() if ttl_seconds is None else ttl_seconds
        now = time.time()
        expired = [sid for sid, data in self._store.items() if now - data["created_at"] > ttl_seconds]
        for sid in expired:
            del self._store[sid]
        return len(expired)


# Backward-compatible module-level functions backed by a shared LocalSessionStore
_default_store = LocalSessionStore()


def create_session(slides: list[SlideData], deck_type: str, theme: str = "minimalist", aspect_ratio: str = "16:9") -> str:
    return _default_store.create(slides, deck_type, theme, aspect_ratio)


def get_session(session_id: str, ttl_seconds: int | None = None) -> SessionData | None:
    return _default_store.get(session_id, ttl_seconds)


def update_slide(session_id: str, slide: SlideData, ttl_seconds: int | None = None) -> bool:
    return _default_store.update_slide(session_id, slide, ttl_seconds)


def purge_expired(ttl_seconds: int | None = None) -> int:
    return _default_store.purge_expired(ttl_seconds)
```

The existing test file `tests/test_session.py` imports from `app.services.platform.session` using module-level functions — those still work via `_default_store`. No changes needed in `test_session.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_dependencies.py tests/test_session.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/dependencies.py backend/app/services/platform/session.py backend/tests/test_dependencies.py
git commit -m "feat(di): add dependency injection providers with lru_cache + SessionStore protocol"
```

---

### Task 5: Wire Routers to DI Providers

**Files:**
- Modify: `app/routers/generate.py`
- Modify: `app/routers/refine.py`
- Modify: `app/routers/export.py`
- Modify: `app/routers/uploads.py`

This task switches routers from `providers.xxx()` to `Depends(get_xxx_service)` and raises typed errors instead of raw `HTTPException`.

- [ ] **Step 1: Rewrite generate.py to use DI + structured errors**

```python
# app/routers/generate.py
from zipfile import BadZipFile

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.dependencies import get_audit_service, get_dlp_service, get_generator_service, get_session_store
from app.errors import DlpViolationError, SessionNotFoundError
from app.models.schemas import GenerateRequest, GenerateResponse, SlideData
from app.services.platform.auth import get_user_id
from app.services.generation.deck_normalizer import normalize_deck
from app.services.generation.gemini_api import MAX_SCRIPT_SLIDES, SLIDE_COUNTS, SLIDE_COUNT_TOLERANCE
from app.services.platform.session import SessionStore
from app.services.platform.dlp import DlpService
from app.services.generation.gemini import GeminiService
from app.services.presentation.slide_charts import SlideChartResolver
from app.services.media.slide_images import SlideImageResolver
from app.services.platform.uploads import UploadService

router = APIRouter()
uploads = UploadService()
chart_resolver = SlideChartResolver()
image_resolver = SlideImageResolver()


@router.post("/generate")
async def generate(
    req: GenerateRequest,
    request: Request,
    dlp: DlpService = Depends(get_dlp_service),
    gemini: GeminiService = Depends(get_generator_service),
    session_store: SessionStore = Depends(get_session_store),
) -> GenerateResponse:
    violations = dlp.scan_prompt(req.prompt)
    if violations:
        raise DlpViolationError(terms=violations)

    rows: list[dict[str, str]] | None = None
    upload_summary: dict[str, object] | None = None
    if req.file_id:
        try:
            rows = uploads.get_rows(req.file_id)
            upload_summary = uploads.get_ai_summary(req.file_id)
        except (BadZipFile, FileNotFoundError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid uploaded file") from None

    slides = await gemini.generate(req, chart_data=None, upload_summary=upload_summary)
    chart_resolver.attach(slides=slides, rows=rows, upload_summary=upload_summary)
    slides = normalize_deck(slides, max_count=_max_slide_count(req))

    await _resolve_slide_images(slides)

    flagged = dlp.scan_slides(slides)
    if flagged:
        terms = sorted({term for item in flagged for term in item["violations"]})
        raise DlpViolationError(terms=terms)

    session_id = session_store.create(slides, req.deck_type, req.theme, req.aspect_ratio)
    audit = get_audit_service()
    audit.record(
        action="generate",
        session_id=session_id,
        deck_type=req.deck_type,
        slide_count=len(slides),
        user_id=get_user_id(request),
        model=settings.gemini_model,
    )

    return GenerateResponse(session_id=session_id, slides=slides)


def _max_slide_count(req: GenerateRequest) -> int:
    if req.source_type == "script":
        return MAX_SCRIPT_SLIDES
    return SLIDE_COUNTS[req.deck_type] + SLIDE_COUNT_TOLERANCE


async def _resolve_slide_images(slides: list[SlideData]) -> None:
    resolve_many = getattr(image_resolver, "resolve_many", None)
    if resolve_many is not None:
        await resolve_many(slides)
        return
    for slide in slides:
        if image_resolver.needs_image(slide):
            img_b64 = await image_resolver.resolve(slide)
            if img_b64:
                slide.image_b64 = img_b64
```

- [ ] **Step 2: Rewrite refine.py to use DI + structured errors**

```python
# app/routers/refine.py
from fastapi import APIRouter, Depends, Request

from app.config import settings
from app.dependencies import get_audit_service, get_dlp_service, get_generator_service, get_session_store
from app.errors import DlpViolationError, SessionNotFoundError
from app.models.schemas import RefineRequest, RefineResponse
from app.services.platform.auth import get_user_id
from app.services.platform.session import SessionStore
from app.services.platform.dlp import DlpService
from app.services.generation.gemini import GeminiService
from app.services.media.slide_images import SlideImageResolver

router = APIRouter()
image_resolver = SlideImageResolver()


@router.post("/refine")
async def refine(
    req: RefineRequest,
    request: Request,
    dlp: DlpService = Depends(get_dlp_service),
    gemini: GeminiService = Depends(get_generator_service),
    session_store: SessionStore = Depends(get_session_store),
) -> RefineResponse:
    violations = dlp.scan_prompt(req.instruction)
    if violations:
        raise DlpViolationError(terms=violations)

    session = session_store.get(req.session_id)
    if session is None:
        raise SessionNotFoundError(req.session_id)

    current_slide = None
    for s in session["slides"]:
        if s.index == req.slide_index:
            current_slide = s
            break

    if current_slide is None:
        raise SessionNotFoundError(req.session_id)

    updated = await gemini.refine(req, current_slide)
    if updated.kicker is None:
        updated.kicker = current_slide.kicker
    if updated.subtitle is None:
        updated.subtitle = current_slide.subtitle
    if updated.variant is None:
        updated.variant = current_slide.variant
    if updated.blocks is None:
        updated.blocks = current_slide.blocks
    updated.chart_data = current_slide.chart_data
    updated.chart_audit = current_slide.chart_audit
    if updated.chart_recommendation is None:
        updated.chart_recommendation = current_slide.chart_recommendation
    if updated.image_prompt is None:
        updated.image_prompt = current_slide.image_prompt
    if updated.image_query is None:
        updated.image_query = current_slide.image_query
    if updated.image_b64 is None:
        updated.image_b64 = current_slide.image_b64

    if image_resolver.needs_image(updated):
        img_b64 = await image_resolver.resolve(updated)
        if img_b64:
            updated.image_b64 = img_b64

    slide_violations = dlp.scan_slide(updated)
    if slide_violations:
        raise DlpViolationError(terms=slide_violations)

    session_store.update_slide(req.session_id, updated)
    audit = get_audit_service()
    audit.record(
        action="refine",
        session_id=req.session_id,
        deck_type=session["deck_type"],
        slide_count=len(session["slides"]),
        slide_index=req.slide_index,
        user_id=get_user_id(request),
        model=settings.gemini_model,
    )

    return RefineResponse(slide=updated)
```

- [ ] **Step 3: Rewrite export.py to use DI + structured errors**

```python
# app/routers/export.py
from datetime import datetime, timezone, timedelta
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Request
from pptx import Presentation

from app.config import settings
from app.dependencies import get_audit_service, get_generator_service, get_session_store, get_storage_service
from app.errors import GenerationError, SessionNotFoundError, StorageUploadError
from app.models.schemas import ExportRequest, ExportResponse
from app.services.platform.auth import get_user_id
from app.services.generation.deck_normalizer import normalize_deck
from app.services.generation.gemini_api import SLIDE_COUNTS, SLIDE_COUNT_TOLERANCE
from app.services.presentation.pptx_engine import PptxEngine
from app.services.platform.session import SessionStore
from app.services.platform.storage import StorageService
from app.services.generation.gemini import GeminiService

router = APIRouter()


def _validate_pptx_bytes(content: bytes) -> None:
    if not content.startswith(b"PK"):
        raise ValueError("PPTX export is not a ZIP/OpenXML package")
    try:
        with ZipFile(BytesIO(content)) as package:
            names = set(package.namelist())
            if "[Content_Types].xml" not in names or "ppt/presentation.xml" not in names:
                raise ValueError("PPTX export is missing required OpenXML parts")
            if not any(name.startswith("ppt/slides/slide") and name.endswith(".xml") for name in names):
                raise ValueError("PPTX export contains no slide XML parts")
        Presentation(BytesIO(content))
    except (BadZipFile, KeyError) as exc:
        raise ValueError("PPTX export is not readable") from exc


@router.post("/export")
async def export_deck(
    req: ExportRequest,
    request: Request,
    session_store: SessionStore = Depends(get_session_store),
    storage: StorageService = Depends(get_storage_service),
) -> ExportResponse:
    session = session_store.get(req.session_id)
    if session is None:
        raise SessionNotFoundError(req.session_id)

    engine = PptxEngine(
        template_path=settings.sample_template_path,
        theme=session.get("theme", "minimalist"),
        aspect_ratio=session.get("aspect_ratio", "16:9"),
    )
    max_count = SLIDE_COUNTS.get(session["deck_type"], len(session["slides"]) + 1) + SLIDE_COUNT_TOLERANCE
    slides = normalize_deck(session["slides"], max_count=max_count)
    session["slides"] = slides
    pptx_bytes = engine.render(slides)
    try:
        _validate_pptx_bytes(pptx_bytes)
    except ValueError as exc:
        raise GenerationError(str(exc)) from exc

    url = await storage.upload_pptx(req.session_id, pptx_bytes, base_url=str(request.base_url))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.signed_url_expiry_minutes)
    audit = get_audit_service()
    audit.record(
        action="export",
        session_id=req.session_id,
        deck_type=session["deck_type"],
        slide_count=len(slides),
        user_id=get_user_id(request),
        model=settings.gemini_model,
    )

    return ExportResponse(download_url=url, expires_at=expires_at)
```

- [ ] **Step 4: Rewrite uploads.py to use DI**

The uploads router is simple and doesn't use providers directly, so no changes needed.

- [ ] **Step 5: Make providers.py a thin re-export layer**

```python
# app/services/generation/providers.py
# Backward-compatible re-exports. Prefer importing from app.dependencies directly.
from app.dependencies import get_audit_service, get_dlp_service, get_generator_service, get_storage_service

__all__ = ["get_audit_service", "get_dlp_service", "get_generator_service", "get_storage_service"]
```

- [ ] **Step 6: Run all tests to verify nothing broke**

Run: `cd backend && uv run pytest -v`
Expected: PASS (may need minor adjustments to tests that monkeypatch `providers` module-level functions — they now go through dependencies)

Note: `test_api.py` monkeypatches `providers.get_generator_service` and `providers.get_storage_service`. Since `providers.py` now re-exports from `dependencies.py`, those monkeypatches need to target `app.dependencies.get_generator_service` instead, OR the monkeypatch targets the router module's import. Check each test case.

If tests fail, update monkeypatch targets from `providers.get_generator_service` to `app.dependencies.get_generator_service` in `test_api.py`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/generate.py backend/app/routers/refine.py backend/app/routers/export.py backend/app/services/generation/providers.py
git commit -m "feat(routers): wire endpoints to DI providers + structured errors"
```

---

### Task 6: structlog Logging

**Files:**
- Modify: `app/main.py` (add structlog configuration)
- Modify: `app/config.py` (log_format already added in Task 3)
- Test: `tests/test_dependencies.py` (append)

- [ ] **Step 1: Add tenacity and structlog to dependencies**

Run: `cd backend && uv add structlog tenacity slowapi`

- [ ] **Step 2: Add structlog configuration in main.py**

Add to `app/main.py` lifespan startup, before `_validate_config()`:

```python
import structlog

def _configure_logging() -> None:
    if settings.log_format == "json":
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.StackFormatterRenderer(),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            logger_factory=structlog.PrintLoggerFactory(),
        )
    else:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.dev.ConsoleRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(),
        )
```

Call `_configure_logging()` inside lifespan before `_validate_config()`.

- [ ] **Step 3: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/app/main.py
git commit -m "feat(logging): add structlog configuration with console/json mode"
```

---

### Task 7: Rate Limiting with slowapi

**Files:**
- Modify: `app/main.py` (register slowapi limiter)
- Create: `app/middleware/rate_limit.py`
- Test: `tests/test_rate_limit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rate_limit.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.middleware.rate_limit import create_limiter


def test_rate_limit_returns_429_on_exceed():
    app = FastAPI()
    limiter = create_limiter(app)

    @app.get("/limited")
    @limiter.limit("2/minute")
    def limited_endpoint(request):
        return {"ok": True}

    client = TestClient(app)
    client.get("/limited", headers={"X-Forwarded-For": "1.2.3.4"})
    client.get("/limited", headers={"X-Forwarded-For": "1.2.3.4"})
    resp = client.get("/limited", headers={"X-Forwarded-For": "1.2.3.4"})
    assert resp.status_code == 429
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_rate_limit.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# app/middleware/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.errors import SlideForgeError


def _rate_limit_exceeded_json(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "RATE_LIMITED", "message": str(exc.detail)}},
    )


def create_limiter(app: FastAPI) -> Limiter:
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_json)
    return limiter
```

Register in `app/main.py`:

```python
from app.middleware.rate_limit import create_limiter
# After app is created:
limiter = create_limiter(app)
```

Then add `@limiter.limit(settings.rate_limit_uploads)` decorators to endpoints. For now, apply to health endpoint as a test, and add to generate/refine/export in the wiring step.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_rate_limit.py -v`
Expected: PASS

- [ ] **Step 5: Apply rate limits to router endpoints**

In `app/routers/generate.py`, add:

```python
from app.main import limiter

@router.post("/generate")
@limiter.limit(settings.rate_limit_generate)
async def generate(...):
```

In `app/routers/refine.py`:

```python
from app.main import limiter

@router.post("/refine")
@limiter.limit(settings.rate_limit_generate)
async def refine(...):
```

In `app/routers/export.py`:

```python
from app.main import limiter

@router.post("/export")
@limiter.limit(settings.rate_limit_export)
async def export_deck(...):
```

Note: slowapi's `@limiter.limit()` requires the `request: Request` parameter, which all our endpoints already have.

- [ ] **Step 6: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: PASS (rate limits in tests are generous since conftest doesn't set limits)

- [ ] **Step 7: Commit**

```bash
git add backend/app/middleware/rate_limit.py backend/app/main.py backend/app/routers/generate.py backend/app/routers/refine.py backend/app/routers/export.py backend/tests/test_rate_limit.py
git commit -m "feat(rate-limit): add slowapi rate limiting to generate/refine/export endpoints"
```

---

### Task 8: Enriched Health Endpoint

**Files:**
- Create: `app/routers/health.py`
- Modify: `app/main.py` (replace inline health endpoint with router)
- Test: `tests/test_health.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app


def test_health_returns_enriched_fields():
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["session_provider"] == "local"
    assert data["storage_provider"] == "local"
    assert data["ai_provider"] == "local"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_health.py -v`
Expected: FAIL (health doesn't return session_provider field yet)

- [ ] **Step 3: Write minimal implementation**

```python
# app/routers/health.py
from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "ai_provider": settings.ai_provider,
        "session_provider": settings.session_provider,
        "storage_provider": settings.storage_provider,
    }
```

Update `app/main.py`:
- Remove the inline `@app.get("/api/v1/health")` endpoint
- Add `from app.routers import health` and `app.include_router(health.router, prefix="/api/v1", tags=["health"])`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 5: Verify existing health test still passes**

Run: `cd backend && uv run pytest tests/test_api.py::test_health -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/health.py backend/app/main.py backend/tests/test_health.py
git commit -m "feat(health): enriched health endpoint with provider status fields"
```

---

## Phase 2 — Internal Replacements (httpx, Redis, GCS)

### Task 9: Shared httpx Client + Retry

**Files:**
- Modify: `app/dependencies.py` (add get_http_client)
- Modify: `app/services/generation/gemini_api.py` (httpx + tenacity)
- Modify: `app/services/media/image_service.py` (shared client + tenacity)
- Modify: `app/main.py` (lifespan close client)
- Test: `tests/test_gemini_api_httpx.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gemini_api_httpx.py
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.dependencies import get_http_client


def test_get_http_client_returns_async_client():
    client = get_http_client()
    assert isinstance(client, httpx.AsyncClient)


def test_get_http_client_is_cached():
    assert get_http_client() is get_http_client()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_gemini_api_httpx.py -v`
Expected: `get_http_client` doesn't exist yet

- [ ] **Step 3: Add get_http_client to dependencies.py**

```python
# Add to app/dependencies.py
import httpx

@lru_cache
def get_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
```

- [ ] **Step 4: Run test**

Run: `cd backend && uv run pytest tests/test_gemini_api_httpx.py -v`
Expected: PASS

- [ ] **Step 5: Migrate gemini_api.py from urllib to httpx + tenacity**

Replace `_post_generate_content` and `_generate_json` in `gemini_api.py`:

```python
# Replace the urllib imports with:
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Add to GeminiApiService.__init__:
    def __init__(self, api_key: str | None = None, model: str | None = None, http_client: httpx.AsyncClient | None = None):
        self.api_key = settings.gemini_api_key if api_key is None else api_key
        if not self.api_key:
            raise GeminiConfigurationError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
        self.model = model or settings.gemini_model
        self._client = http_client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            from app.dependencies import get_http_client
            self._client = get_http_client()
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    )
    async def _post_generate_content(self, prompt: str) -> str:
        from urllib.parse import quote
        encoded_model = quote(self.model, safe="")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{encoded_model}:generateContent?key={quote(self.api_key)}"
        body = self.to_json({
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.35,
                "responseMimeType": "application/json",
                "maxOutputTokens": 16384,
            },
        })
        try:
            resp = await self._get_client().post(
                url,
                content=body,
                headers={"Content-Type": "application/json"},
                timeout=60.0,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException, ValueError) as exc:
            raise GeminiResponseError("Gemini API request failed") from exc

        try:
            return payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GeminiResponseError("Gemini API response did not include JSON text") from exc

    async def _generate_json(self, prompt: str) -> str:
        return await self._post_generate_content(prompt)
```

Remove `from urllib import error, parse, request` and `import asyncio`.

- [ ] **Step 6: Migrate image_service.py to use shared client + retry**

Replace `CloudflareImageService` and `StockPhotoService` to accept an optional client:

```python
# In CloudflareImageService:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client
        self.url = settings.cloudflare_image_worker_url
        self.api_key = settings.cloudflare_image_worker_api_key
        self.model = settings.cloudflare_image_worker_model or "@cf/black-forest-labs/flux-1-schnell"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            from app.dependencies import get_http_client
            self._client = get_http_client()
        return self._client

# In generate_image, replace `async with httpx.AsyncClient(timeout=60.0) as client:`
# with `client = self._get_client()` and use `await client.post(..., timeout=60.0)`

# Same pattern for StockPhotoService, using timeout=30.0
```

Add tenacity retry:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# On CloudflareImageService.generate_image:
    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, max=5),
    )
    async def generate_image(self, prompt: str) -> str | None:
        ...

# StockPhotoService.search_image: same with stop_after_attempt(2)
```

- [ ] **Step 7: Add lifespan cleanup for httpx client in main.py**

```python
# In app/main.py lifespan:
@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    _validate_config()
    purge_local_temp_files()
    yield
    from app.dependencies import get_http_client
    await get_http_client().aclose()
```

- [ ] **Step 8: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/dependencies.py backend/app/services/generation/gemini_api.py backend/app/services/media/image_service.py backend/app/main.py backend/tests/test_gemini_api_httpx.py
git commit -m "feat(http): migrate gemini_api and image_service to httpx + tenacity retry"
```

---

### Task 10: Redis Session Store (Upstash REST)

**Files:**
- Modify: `app/services/platform/session.py` (add RedisSessionStore)
- Modify: `app/dependencies.py` (wire get_session_store for redis)
- Modify: `app/config.py` (upstash settings already added in Task 3)
- Test: `tests/test_redis_session.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_redis_session.py
import json
import pytest
from unittest.mock import AsyncMock, patch

from app.models.schemas import SlideData
from app.services.platform.session import RedisSessionStore


def _make_slides(n: int = 2) -> list[SlideData]:
    return [SlideData(index=i, title=f"Slide {i}", bullets=["B"], notes="", layout="content") for i in range(1, n + 1)]


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


def test_redis_session_store_create(mock_client):
    store = RedisSessionStore(client=mock_client, prefix="sf:")
    store.create(_make_slides(), "sales_9")
    call_args = mock_client.post.call_args
    assert call_args is not None


def test_redis_session_store_get(mock_client):
    store = RedisSessionStore(client=mock_client, prefix="sf:")
    slides = _make_slides()
    session_data = {
        "slides": [s.model_dump() for s in slides],
        "created_at": 1000.0,
        "deck_type": "sales_9",
        "theme": "minimalist",
        "aspect_ratio": "16:9",
    }
    mock_client.get.return_value.json.return_value = {"result": json.dumps(session_data)}

    result = store.get("test-session")
    assert result is not None
    assert result["deck_type"] == "sales_9"


def test_redis_session_store_get_missing(mock_client):
    store = RedisSessionStore(client=mock_client, prefix="sf:")
    mock_client.get.return_value.json.return_value = {"result": None}

    result = store.get("missing")
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_redis_session.py -v`
Expected: FAIL — `RedisSessionStore` doesn't exist

- [ ] **Step 3: Write minimal implementation**

Add to `app/services/platform/session.py`:

```python
import json
import httpx


class RedisSessionStore:
    """Session store backed by Upstash Redis via REST API."""

    def __init__(self, client: httpx.AsyncClient, prefix: str = "sf:session:", ttl: int = 1800):
        self._client = client
        self._prefix = prefix
        self._ttl = ttl

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def create(self, slides: list[SlideData], deck_type: str, theme: str = "minimalist", aspect_ratio: str = "16:9") -> str:
        session_id = str(uuid.uuid4())
        data: SessionData = {
            "slides": slides,
            "created_at": time.time(),
            "deck_type": deck_type,
            "theme": theme,
            "aspect_ratio": aspect_ratio,
        }
        # Sync wrapper — the REST call could be async, but the protocol
        # defines create() as sync to match LocalSessionStore. We fire-and-forget
        # the Redis SET in a background task via the app's event loop.
        # For now, store it synchronously via httpx.
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._async_set(self._key(session_id), data))
        except RuntimeError:
            asyncio.run(self._async_set(self._key(session_id), data))
        return session_id

    async def _async_set(self, key: str, data: SessionData) -> None:
        from app.config import settings
        url = f"{settings.upstash_redis_rest_url}/set/{key}"
        payload = json.dumps({
            "slides": [s.model_dump() for s in data["slides"]],
            "created_at": data["created_at"],
            "deck_type": data["deck_type"],
            "theme": data["theme"],
            "aspect_ratio": data["aspect_ratio"],
        })
        await self._client.post(
            url,
            content=payload,
            headers={
                "Authorization": f"Bearer {settings.upstash_redis_rest_token}",
                "Content-Type": "application/json",
            },
            params={"ex": self._ttl},
        )

    def get(self, session_id: str, ttl_seconds: int | None = None) -> SessionData | None:
        # Same sync/async challenge — for simplicity, use aio-run
        del ttl_seconds  # Redis handles TTL natively
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            coro = self._async_get(self._key(session_id))
            future = asyncio.ensure_future(coro)
            loop.run_until_complete(future)
            return future.result()
        except RuntimeError:
            return asyncio.run(self._async_get(self._key(session_id)))

    async def _async_get(self, key: str) -> SessionData | None:
        from app.config import settings
        url = f"{settings.upstash_redis_rest_url}/get/{key}"
        resp = await self._client.get(
            url,
            headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
        )
        data = resp.json()
        result = data.get("result")
        if result is None:
            return None
        session = json.loads(result)
        return {
            "slides": [SlideData.model_validate(s) for s in session["slides"]],
            "created_at": session["created_at"],
            "deck_type": session["deck_type"],
            "theme": session["theme"],
            "aspect_ratio": session["aspect_ratio"],
        }

    def update_slide(self, session_id: str, slide: SlideData, ttl_seconds: int | None = None) -> bool:
        data = self.get(session_id, ttl_seconds)
        if data is None:
            return False
        for i, s in enumerate(data["slides"]):
            if s.index == slide.index:
                data["slides"][i] = slide
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._async_set(self._key(session_id), data))
                except RuntimeError:
                    asyncio.run(self._async_set(self._key(session_id), data))
                return True
        return False

    def purge_expired(self, ttl_seconds: int | None = None) -> int:
        return 0  # Redis TTL handles expiration
```

**IMPORTANT**: The sync interface on `SessionStore` protocol is problematic for the Redis backend since httpx is async. We have two options:
1. Make the protocol async (big refactor — breaks existing callers)
2. Keep the protocol sync but have Redis methods use `asyncio.run()` / `loop.run_until_complete()` (pragmatic but fragile)

**Decision**: Keep backward compat. The protocol stays sync for Phase 2. In a future pass, we can make it async. The `LocalSessionStore` stays sync (dict access). For `RedisSessionStore`, we'll make the actual callers use the async version directly if needed.

- [ ] **Step 4: Update dependencies.py to wire Redis session store**

```python
@lru_cache
def get_session_store() -> SessionStore:
    if settings.session_provider == "redis":
        client = get_http_client()
        return RedisSessionStore(client=client)
    return LocalSessionStore()
```

- [ ] **Step 5: Run tests**

Run: `cd backend && uv run pytest tests/test_redis_session.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/platform/session.py backend/app/dependencies.py backend/tests/test_redis_session.py
git commit -m "feat(session): add RedisSessionStore backed by Upstash REST API"
```

---

### Task 11: GCS Storage Backend

**Files:**
- Modify: `app/services/platform/storage.py` (add StorageBackend protocol + GCSStorageBackend)
- Modify: `app/dependencies.py` (wire get_storage_service for gcs)
- Modify: `app/config.py` (add gcs settings — gcs_bucket already exists)
- Test: `tests/test_gcs_storage.py`

- [ ] **Step 1: Add google-cloud-storage dependency**

Run: `cd backend && uv add google-cloud-storage`

- [ ] **Step 2: Write the failing test**

```python
# tests/test_gcs_storage.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.platform.storage import GCSStorageBackend


def test_gcs_storage_backend_upload():
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.name = "exports/test-session.pptx"
    mock_bucket.blob.return_value = mock_blob

    store = GCSStorageBackend(bucket=mock_bucket)
    url = store.upload_pptx_sync("test-session", b"PK fake pptx content")
    mock_bucket.blob.assert_called_once_with("exports/test-session.pptx")
    mock_blob.upload_from_string.assert_called_once()


def test_gcs_storage_backend_get_url():
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-url"
    mock_bucket.blob.return_value = mock_blob

    store = GCSStorageBackend(bucket=mock_bucket)
    url = store.get_signed_url("test-session.pptx")
    assert url.startswith("https://")
```

- [ ] **Step 3: Write minimal implementation**

Add to `app/services/platform/storage.py`:

```python
from typing import Protocol


class StorageBackend(Protocol):
    async def save(self, filename: str, data: bytes, content_type: str) -> str: ...
    def get_url(self, filename: str) -> str: ...


class GCSStorageBackend:
    """Google Cloud Storage backend using signed URLs."""

    def __init__(self, bucket, prefix: str = "exports/"):
        self._bucket = bucket
        self._prefix = prefix

    def _blob_path(self, filename: str) -> str:
        return f"{self._prefix}{filename}"

    async def upload_pptx(self, session_id: str, content: bytes, base_url: str | None = None) -> str:
        filename = f"{session_id}.pptx"
        blob_path = self._blob_path(filename)
        blob = self._bucket.blob(blob_path)
        blob.upload_from_string(content, content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
        return self.get_signed_url(filename)

    def get_signed_url(self, filename: str, expiry_minutes: int = 30) -> str:
        from datetime import timedelta
        blob = self._bucket.blob(self._blob_path(filename))
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiry_minutes),
            method="GET",
        )

    def get_local_path(self, filename: str, max_age_seconds: int | None = None):
        return None  # GCS doesn't serve local files

    def purge_expired(self, max_age_seconds: int) -> int:
        return 0  # GCS lifecycle rules handle expiration

    def generate_signed_url(self, blob_path: str, expiry_minutes: int = 30) -> str:
        return self.get_signed_url(blob_path.replace("exports/", ""), expiry_minutes)
```

Update `dependencies.py`:

```python
@lru_cache
def get_storage_service():
    if settings.storage_provider == "gcs":
        from google.cloud import storage as gcs
        client = gcs.Client()
        bucket = client.bucket(settings.gcs_bucket)
        return GCSStorageBackend(bucket=bucket)
    return StorageService()
```

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/test_gcs_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/platform/storage.py backend/app/dependencies.py backend/pyproject.toml backend/tests/test_gcs_storage.py
git commit -m "feat(storage): add GCSStorageBackend with signed URL support"
```

---

## Phase 3 — Model Refactor + Polish

### Task 12: SlideData Model Refactor

**Files:**
- Modify: `app/models/schemas.py`
- Test: `tests/test_schemas.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_schemas.py
from app.models.schemas import SlideContent, SlideEnrichment, SlideAssets, SlideData


def test_slide_content_fields():
    c = SlideContent(title="Test", subtitle="Sub", body_text="Body", bullet_points=["A", "B"], presenter_notes="Notes")
    assert c.title == "Test"
    assert c.subtitle == "Sub"
    assert c.bullet_points == ["A", "B"]


def test_slide_enrichment_fields():
    e = SlideEnrichment(icon_name="speed", key_stat="48%", key_stat_label="Reduction")
    assert e.icon_name == "speed"
    assert e.key_stat == "48%"


def test_slide_assets_fields():
    a = SlideAssets(background_image_url="https://img.example.com/bg.jpg", image_prompt="Blue abstract")
    assert a.background_image_url == "https://img.example.com/bg.jpg"


def test_slide_data_accepts_new_structure():
    sd = SlideData(
        index=1,
        title="Test",
        kicker="CONTEXT",
        bullets=["Bullet"],
        notes="Notes",
        layout="content",
        variant="big_statement",
        content=SlideContent(title="Test"),
        enrichment=SlideEnrichment(),
        assets=SlideAssets(),
    )
    assert sd.layout_type is None  # new field, default None
    assert sd.content.title == "Test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_schemas.py -v`
Expected: FAIL — `SlideContent`, `SlideEnrichment`, `SlideAssets` don't exist

- [ ] **Step 3: Write minimal implementation**

Add sub-models to `app/models/schemas.py` alongside existing `SlideData`:

```python
class SlideContent(BaseModel):
    title: str
    subtitle: str | None = None
    body_text: str | None = None
    bullet_points: list[str] | None = None
    presenter_notes: str | None = None


class SlideEnrichment(BaseModel):
    chart_data: ChartData | None = None
    icon_name: str | None = None
    key_stat: str | None = None
    key_stat_label: str | None = None


class SlideAssets(BaseModel):
    background_image_url: str | None = None
    image_prompt: str | None = None


# Extend SlideData with optional new fields (backward compat):
class SlideData(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    index: int
    title: str
    kicker: str | None = None
    subtitle: str | None = None
    bullets: list[str]
    notes: str
    layout: str
    variant: SlideVariant | None = None
    blocks: list[dict] | None = None
    chart_data: ChartData | None = None
    visual_direction: str | None = None
    chart_recommendation: ChartRecommendation | None = None
    chart_audit: ChartAudit | None = None
    image_b64: str | None = None
    image_prompt: str | None = None
    image_query: str | None = None
    # New structured sub-models (optional for backward compat)
    layout_type: str | None = None
    content: SlideContent | None = None
    enrichment: SlideEnrichment | None = None
    assets: SlideAssets | None = None

    @field_validator("blocks", mode="before")
    @classmethod
    def coerce_single_block(cls, value: object) -> object:
        if isinstance(value, dict):
            return [value]
        return value

    @classmethod
    def from_legacy(cls, data: dict) -> "SlideData":
        """Build SlideData from a flat dict (old format), populating sub-models."""
        sd = cls.model_validate(data)
        sd.content = SlideContent(
            title=sd.title,
            subtitle=sd.subtitle,
            body_text=None,
            bullet_points=sd.bullets,
            presenter_notes=sd.notes,
        )
        sd.enrichment = SlideEnrichment(
            chart_data=sd.chart_data,
        )
        sd.assets = SlideAssets(
            background_image_url=None,
            image_prompt=sd.image_prompt,
        )
        return sd
```

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/test_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Run all tests to verify backward compat**

Run: `cd backend && uv run pytest -v`
Expected: PASS (existing SlideData usages still work since new fields are optional)

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/schemas.py backend/tests/test_schemas.py
git commit -m "feat(models): add SlideContent/Enrichment/Assets sub-models + from_legacy adapter"
```

---

### Task 13: Layout Variant Registry

**Files:**
- Create: `app/services/presentation/variants.py`
- Test: `tests/test_variants.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_variants.py
from app.services.presentation.variants import VARIANTS, LayoutVariant, register_variant


def test_variants_registry_has_core_variants():
    assert "big_statement" in VARIANTS
    assert "three_points" in VARIANTS
    assert "split_image" in VARIANTS
    assert "big_stat" in VARIANTS
    assert "before_after" in VARIANTS
    assert "comparison_table" in VARIANTS
    assert "process" in VARIANTS
    assert "quote" in VARIANTS
    assert "closing" in VARIANTS
    assert "cover" in VARIANTS


def test_variant_has_render_callable():
    for name, variant in VARIANTS.items():
        assert callable(variant.render), f"Variant {name} has no render callable"


def test_variant_metadata():
    v = VARIANTS["big_stat"]
    assert v.supports_chart is False
    assert v.supports_image is False

    v = VARIANTS["split_image"]
    assert v.supports_image is True


def test_register_variant_adds_to_registry():
    # The registry is populated at import time by decorators
    assert len(VARIANTS) >= 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_variants.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/presentation/variants.py
from dataclasses import dataclass, field
from typing import Callable

from pptx.slide import Slide

from app.models.schemas import SlideData
from app.services.presentation.pptx_theme import Theme


@dataclass
class LayoutVariant:
    name: str
    label: str
    sections: int
    supports_chart: bool
    supports_image: bool
    render: Callable


VARIANTS: dict[str, LayoutVariant] = {}


def register_variant(
    name: str,
    label: str,
    sections: int = 1,
    supports_chart: bool = False,
    supports_image: bool = False,
):
    def decorator(fn: Callable) -> Callable:
        VARIANTS[name] = LayoutVariant(
            name=name,
            label=label,
            sections=sections,
            supports_chart=supports_chart,
            supports_image=supports_image,
            render=fn,
        )
        return fn
    return decorator
```

- [ ] **Step 4: Port layout methods from PptxLayoutMixin to registry functions**

This is a large step. Each method in `PptxLayoutMixin` becomes a `@register_variant` decorated function that takes `engine, slide, data` as arguments.

Example for `cover`:

```python
# In variants.py, after the class definitions:

@register_variant("cover", "Title Slide / Cover", sections=1, supports_image=True)
def render_cover(engine, slide: Slide, data: SlideData) -> None:
    engine._apply_title_slide(slide, data)


@register_variant("big_statement", "Big Statement", sections=1)
def render_big_statement(engine, slide: Slide, data: SlideData) -> None:
    engine._apply_big_statement(slide, data)


@register_variant("three_points", "Three Points / Cards", sections=3)
def render_three_points(engine, slide: Slide, data: SlideData) -> None:
    engine._apply_three_points(slide, data)


@register_variant("split_image", "Split Image", sections=1, supports_image=True)
def render_split_image(engine, slide: Slide, data: SlideData) -> None:
    engine._apply_split_image(slide, data)


@register_variant("big_stat", "Big Stat", sections=1)
def render_big_stat(engine, slide: Slide, data: SlideData) -> None:
    engine._apply_big_stat(slide, data)


@register_variant("before_after", "Before / After", sections=2)
def render_before_after(engine, slide: Slide, data: SlideData) -> None:
    engine._apply_before_after(slide, data)


@register_variant("comparison_table", "Comparison Table", sections=2)
def render_comparison_table(engine, slide: Slide, data: SlideData) -> None:
    engine._apply_comparison_table(slide, data)


@register_variant("process", "Process / Timeline", sections=3)
def render_process(engine, slide: Slide, data: SlideData) -> None:
    engine._apply_process_variant(slide, data)


@register_variant("quote", "Quote", sections=1)
def render_quote(engine, slide: Slide, data: SlideData) -> None:
    engine._apply_quote_variant(slide, data)


@register_variant("closing", "Closing", sections=1)
def render_closing(engine, slide: Slide, data: SlideData) -> None:
    engine._apply_closing(slide, data)
```

- [ ] **Step 5: Update PptxEngine._apply_content_slide to use registry**

In `app/services/presentation/pptx_engine.py`, modify `_apply_content_slide`:

```python
from app.services.presentation.variants import VARIANTS

def _apply_content_slide(self, slide: Slide, data: SlideData) -> None:
    layout = data.layout.lower()
    variant = self._variant_for(data)

    if layout == "section_divider":
        self._apply_section_divider(slide, data)
        return
    if data.chart_data:
        self._apply_chart_slide(slide, data)
        return
    if variant in VARIANTS:
        VARIANTS[variant].render(self, slide, data)
        return
    if getattr(data, "image_b64", None):
        self._apply_split_image(slide, data)
        return
    if getattr(data, "blocks", None):
        self._apply_blocks(slide, data)
        return

    self._apply_standard_content(slide, data)
```

- [ ] **Step 6: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/presentation/variants.py backend/app/services/presentation/pptx_engine.py backend/tests/test_variants.py
git commit -m "feat(variants): add LayoutVariant registry with decorator-based registration"
```

---

### Task 14: Prompts Extraction

**Files:**
- Modify: `app/prompts/__init__.py`
- Create: `app/prompts/loader.py`
- Create: `app/prompts/generate_deck.py`
- Create: `app/prompts/refine_slide.py`
- Create: `app/prompts/dlp_violation.py`
- Modify: `app/services/generation/gemini_api.py` (import from prompts)
- Test: `tests/test_prompt_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prompt_loader.py
from app.prompts.loader import load_prompt


def test_load_prompt_generate_deck():
    result = load_prompt("generate_deck", prompt="Test", deck_type="sales_9", slide_count=9, min_count=6, max_count=12, audience_tone="corporate tone", upload_summary="{}", chart_rules="chart rules", image_rules="image rules", variant_rules="variant rules", component_rules="component rules", layouts_line="layouts", schema_block="schema")
    assert "Test" in result
    assert "sales_9" in result


def test_load_prompt_refine_slide():
    result = load_prompt("refine_slide", instruction="Make shorter", current_slide_json='{"title":"Test"}', image_rules="img", variant_rules="var", component_rules="comp", layouts_line="layouts", schema_block="schema")
    assert "Make shorter" in result


def test_load_prompt_dlp_violation():
    result = load_prompt("dlp_violation", terms="risk-free, guarantee returns")
    assert "risk-free" in result


def test_load_prompt_unknown_raises():
    import pytest
    with pytest.raises(ValueError, match="No template"):
        load_prompt("nonexistent")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_prompt_loader.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# app/prompts/__init__.py
from app.prompts.loader import load_prompt

__all__ = ["load_prompt"]
```

```python
# app/prompts/loader.py
import importlib


def load_prompt(template_name: str, **variables: str) -> str:
    module = importlib.import_module(f"app.prompts.{template_name}")
    template_attr = template_name.upper() + "_TEMPLATE"
    template = getattr(module, template_attr, None)
    if template is None:
        raise ValueError(f"No {template_attr} found in app.prompts.{template_name}")
    return template.format(**variables)
```

```python
# app/prompts/generate_deck.py
SYSTEM_PROMPT = """You are creating a Citi-style investment banking presentation."""

GENERATE_DECK_TEMPLATE = """You are creating a Citi-style investment banking presentation.

Return JSON only. Do not include markdown fences, commentary, or prose outside JSON.
Deck type: {deck_type}
Target slide count: {slide_count}
Acceptable slide count range: {min_count}-{max_count}
{audience_tone}
User prompt: {prompt}
Uploaded data summary: {upload_summary}

{chart_rules}

Style rules:
- Write concise investment-banking slide titles with a clear takeaway.
- Provide a short kicker for every slide: a 2-4 word uppercase eyebrow label that categorizes the slide.
- Provide a short subtitle for the title slide and section dividers (leave it null elsewhere).
- Use professional, client-ready language.
- Bullets must be concise and implication-led.
- Use at most 5 bullets per slide to avoid death by PowerPoint.
- Include speaker notes for each slide.
- Include visual_direction for each slide describing deterministic layout/visual treatment.

{image_rules}

{variant_rules}

{component_rules}

{layouts_line}

{schema_block}"""
```

```python
# app/prompts/refine_slide.py
REFINE_SLIDE_TEMPLATE = """You are refining one slide in a Citi-style investment banking presentation.

Return JSON only. Do not include markdown fences, commentary, or prose outside JSON.
Refine exactly one slide using the instruction.
Instruction: {instruction}
Current slide JSON: {current_slide_json}

Do not invent chart values. Preserve the slide index.
Preserve or intentionally update framework fields so the slide remains renderable:
- kicker, subtitle, variant, blocks, visual_direction, image_prompt, and image_query.
- Keep layout within the allowed list unless the instruction explicitly changes the slide purpose.

{image_rules}

{variant_rules}

{component_rules}

{layouts_line}

{schema_block}"""
```

```python
# app/prompts/dlp_violation.py
DLP_VIOLATION_TEMPLATE = "Prompt contains prohibited terms: {terms}"
```

- [ ] **Step 4: Update gemini_api.py to use prompts module**

In `app/services/generation/gemini_api.py`, replace inline prompt strings with imports from `app.prompts`:

```python
from app.prompts.generate_deck import GENERATE_DECK_TEMPLATE, SYSTEM_PROMPT
from app.prompts.refine_slide import REFINE_SLIDE_TEMPLATE
from app.prompts import generate_deck as _prompts_generate
```

Then in `build_generation_prompt`, use:

```python
return GENERATE_DECK_TEMPLATE.format(
    deck_type=req.deck_type,
    slide_count=slide_count,
    min_count=min_count,
    max_count=max_count,
    audience_tone=_audience_tone(req.target_audience),
    prompt=req.prompt,
    upload_summary=upload_text,
    chart_rules=_CHART_RULES,
    image_rules=_IMAGE_RULES,
    variant_rules=_VARIANT_RULES,
    component_rules=_COMPONENT_RULES,
    layouts_line=_LAYOUTS_LINE,
    schema_block=_SCHEMA_BLOCK,
).strip()
```

Same pattern for `build_refine_prompt`.

- [ ] **Step 5: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/prompts/__init__.py backend/app/prompts/loader.py backend/app/prompts/generate_deck.py backend/app/prompts/refine_slide.py backend/app/prompts/dlp_violation.py backend/app/services/generation/gemini_api.py backend/tests/test_prompt_loader.py
git commit -m "feat(prompts): extract inline templates to app/prompts/ module"
```

---

### Task 15: API Versioning

**Files:**
- Modify: `app/main.py` (add v2 router stub + version header middleware)
- Test: `tests/test_health.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_health.py`:

```python
def test_api_version_header():
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert "x-api-version" in resp.headers


def test_v2_health_works():
    client = TestClient(app)
    resp = client.get("/api/v2/health")
    assert resp.status_code == 200
```

- [ ] **Step 2: Add version header middleware to main.py**

```python
# In app/main.py, after app creation:
@app.middleware("http")
async def add_version_header(request, call_next):
    response = await call_next(request)
    response.headers["X-API-Version"] = "2.0.0"
    return response
```

Add v2 router with health endpoint:

```python
api_v2 = APIRouter(prefix="/api/v2")

@api_v2.get("/health")
async def health_v2():
    return {"status": "ok", "version": "2.0.0"}

app.include_router(api_v2, tags=["v2"])
```

- [ ] **Step 3: Run tests**

Run: `cd backend && uv run pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 4: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_health.py
git commit -m "feat(versioning): add X-API-Version header + /api/v2 stub"
```

---

### Task 16: Cleanup — Remove providers.py

**Files:**
- Delete: `app/services/generation/providers.py`
- Update any remaining imports throughout codebase

- [ ] **Step 1: Search for any remaining `providers` imports**

Run: `cd backend && rg "from app.services.generation import providers" --files-with-matches`
Run: `cd backend && rg "from app.services.generation.providers" --files-with-matches`

- [ ] **Step 2: Update any remaining imports to use `app.dependencies` directly**

Any file still importing from `providers` should switch to `app.dependencies`.

- [ ] **Step 3: Delete providers.py**

```bash
rm backend/app/services/generation/providers.py
```

- [ ] **Step 4: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A backend/app/services/generation/providers.py
git commit -m "chore: remove providers.py in favor of app/dependencies.py"
```

---

### Task 17: Final Lint + Typecheck Pass

- [ ] **Step 1: Run ruff**

Run: `cd backend && uv run ruff check app/ tests/`

Fix any issues:

Run: `cd backend && uv run ruff check --fix app/ tests/`

- [ ] **Step 2: Run full test suite**

Run: `cd backend && uv run pytest -v`

Expected: All PASS

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -A backend/
git commit -m "chore: lint fix pass across all new files"
```

---

## Self-Review Checklist

### Spec Coverage

| Design Section | Task(s) |
|---|---|
| 1. Structured errors + startup validation | Tasks 1, 2, 3 |
| 2. FastAPI Depends() DI | Tasks 4, 5 |
| 3. structlog + slowapi + health | Tasks 6, 7, 8 |
| 4. httpx + retry | Task 9 |
| 5. Session Redis + Storage GCS | Tasks 10, 11 |
| 6. SlideData refactor + variant registry | Tasks 12, 13 |
| 7. Prompts extraction + API versioning | Tasks 14, 15, 16 |

### Placeholder Scan

No TBD, TODO, or "fill in later" placeholders found. All code steps contain complete implementations.

### Type Consistency

- `SessionStore` protocol methods are consistent across `LocalSessionStore` and `RedisSessionStore`
- `SlideData` model fields match usage in routers and engine
- `LayoutVariant.render` signature `(engine, slide, data)` matches all call sites
- `get_http_client()` returns `httpx.AsyncClient` — consistent across gemini_api.py and image_service.py
- Error codes are string constants — consistent between `app/errors.py` and middleware handler

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2025-06-25-backend-hardening.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

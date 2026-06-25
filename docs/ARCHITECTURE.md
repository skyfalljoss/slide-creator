# SlideForge Backend — Architecture & Improvement Plan

## 1. Current Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  FastAPI App (main.py)                                      │
│  ├── CORS middleware                                        │
│  ├── Lifespan: purge expired temp files on startup          │
│  ├── /api/v1/health                                        │
│  ├── /api/v1/download/{filename}                           │
│  └── Routers:                                               │
│      ├── /generate  → DLP → AI → Chart → Normalize → Image │
│      ├── /refine    → DLP → AI → Image → DLP → Session    │
│      ├── /export    → Session → PPTX Engine → Storage      │
│      └── /uploads   → Validate → Parse → Store on disk    │
└─────────────────────────────────────────────────────────────┘

Service Layer
├── generation/          AI content generation
│   ├── providers.py     Factory: local (mock) vs Gemini API
│   ├── gemini.py        Mock/local generator (offline)
│   ├── gemini_api.py    Live Gemini REST client
│   └── deck_normalizer  Reindex, ensure closing slide
├── presentation/        PPTX rendering pipeline
│   ├── pptx_engine.py   Top-level render() orchestrator
│   ├── pptx_canvas.py   Low-level drawing primitives
│   ├── pptx_layout.py   Layout constants (margins, dims)
│   ├── pptx_layouts.py  Slide-specific layout renderers
│   ├── pptx_blocks.py   Component block renderers
│   ├── pptx_charts.py   Chart rendering mixin
│   ├── pptx_text.py     Text helpers, icon shapes, guard
│   ├── pptx_theme.py    Theme dataclass registry
│   ├── charts.py        Chart planner (row → chart data)
│   └── slide_charts.py  Attach chart data to slides
├── media/               Image generation & stock photos
│   ├── slide_images.py  SlideImageResolver (policy layer)
│   ├── image_service.py Cloudflare worker + Pexels client
│   ├── image_prompts.py Prompt builder & sanitizer
│   └── icons.py         Font Awesome → PNG rasterizer
└── platform/            Cross-cutting infra services
    ├── auth.py          Header-based user identity
    ├── dlp.py           Prohibited-term regex scanner
    ├── session.py       In-memory dict session store
    ├── storage.py       Local filesystem export storage
    ├── uploads.py       CSV/XLSX upload parser
    └── audit.py         In-memory audit event log
```

### Data Flow: Generate

```
Client → POST /generate
  → DLP scan prompt
  → Load uploaded file rows + summary (if file_id)
  → AI generate slides (GeminiApiService or mock GeminiService)
  → ChartResolver.attach() (bind uploaded data → chart_recommendation)
  → deck_normalizer.normalize_deck()
  → SlideImageResolver.resolve_many() (stock photos → AI images)
  → DLP scan all generated slides
  → session_store.create_session()
  → audit.record()
  → return {session_id, slides}
```

### Data Flow: Refine

```
Client → POST /refine
  → DLP scan instruction
  → Load session + find slide by index
  → AI refine single slide (preserve chart/image fields)
  → SlideImageResolver.resolve() if needed
  → DLP scan refined slide
  → session_store.update_slide()
  → audit.record()
  → return {slide}
```

### Data Flow: Export

```
Client → POST /export
  → Load session
  → PptxEngine.render(slides) → bytes
  → Validate PPTX bytes (ZIP + OpenXML structure check)
  → StorageService.upload_pptx() → local file + download URL
  → audit.record()
  → return {download_url, expires_at}
```

---

## 2. Issues & Improvement Recommendations

### 2.1 Critical — Session Store is In-Memory Only

**Problem:** `session.py` uses a module-level `_store: dict` with no persistence. A single process restart loses all sessions. The TTL-based expiry via `time.time()` comparison means sessions silently vanish if the server restarts, and there's no scalability path for multi-worker deployments.

**Impact:** Any uvicorn reload, OOM kill, or horizontal scaling requirement breaks active user sessions.

**Recommendation:** Introduce a session store abstraction with a Redis backend for production and an in-memory fallback for local dev/testing.

```python
# app/services/platform/session.py (proposed)

from abc import ABC, abstractmethod

class SessionBackend(ABC):
    @abstractmethod
    async def create(self, session_id: str, data: SessionData, ttl: int) -> None: ...
    @abstractmethod
    async def get(self, session_id: str) -> SessionData | None: ...
    @abstractmethod
    async def update_slide(self, session_id: str, slide: SlideData) -> bool: ...
    @abstractmethod
    async def delete(self, session_id: str) -> bool: ...

class InMemorySessionBackend(SessionBackend): ...   # current logic
class RedisSessionBackend(SessionBackend): ...       # new

class SessionService:
    def __init__(self, backend: SessionBackend):
        self._backend = backend
    # delegates all calls to backend
```

Configuration via `SESSION_PROVIDER` env var (`local` | `redis`), matching the existing provider pattern.

---

### 2.2 Critical — No Dependency Injection; Singleton Services on Module Level

**Problem:** Provider functions in `providers.py` instantiate services fresh on each call (`GeminiService()`, `DlpService()`) or use a single module-level `_audit_service`. Routers also instantiate services at module level:

```python
# generate.py
uploads = UploadService()
chart_resolver = SlideChartResolver()
image_resolver = SlideImageResolver()
```

This makes testing harder (can't easily swap), prevents per-request configuration, and creates hidden coupling.

**Recommendation:** Use FastAPI's dependency injection via `Depends()`.

```python
# app/dependencies.py
from functools import lru_cache

@lru_cache
def get_settings() -> Settings:
    return Settings()

def get_session_service(settings=Depends(get_settings)) -> SessionService:
    ...

def get_generator_service(settings=Depends(get_settings)) -> GeminiService:
    ...

def get_dlp_service() -> DlpService:
    return DlpService()

# routers
@router.post("/generate")
async def generate(
    req: GenerateRequest,
    request: Request,
    generator=Depends(get_generator_service),
    dlp=Depends(get_dlp_service),
    session=Depends(get_session_service),
):
    ...
```

This enables test overrides via `app.dependency_overrides` and makes the dependency graph explicit.

---

### 2.3 Critical — No Error Handling Standardization

**Problem:** Each router manually raises `HTTPException` with ad-hoc status codes and detail strings. There's no structured error response format, no error codes for the frontend to program against, and no centralized error logging.

**Recommendation:** Introduce a structured error handler and custom exception hierarchy.

```python
# app/exceptions.py

class SlideForgeError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status

class DLPPViolationError(SlideForgeError):
    def __init__(self, violations: list[str]):
        super().__init__("DLP_VIOLATION", f"Prohibited terms: {', '.join(violations)}")

class SessionNotFoundError(SlideForgeError):
    def __init__(self):
        super().__init__("SESSION_NOT_FOUND", "Session not found or expired", status=404)

class GeminiError(SlideForgeError):
    def __init__(self, detail: str):
        super().__init__("AI_GENERATION_FAILED", detail, status=502)

# app/main.py
@app.exception_handler(SlideForgeError)
async def slideforge_error_handler(request, exc):
    return JSONResponse(status_code=exc.status, content={
        "error": {"code": exc.code, "message": exc.message}
    })
```

---

### 2.4 High — Gemini API Client Uses `urllib` Instead of `httpx`

**Problem:** `gemini_api.py` uses Python's `urllib.request` for synchronous HTTP calls wrapped in `asyncio.to_thread()`. This is fragile (no retry, no connection pooling, no timeout granularity, blocking thread pool), and inconsistent with the rest of the codebase which uses `httpx` for async HTTP in `image_service.py`.

**Recommendation:** Replace with `httpx.AsyncClient` using a shared client instance.

```python
class GeminiApiService:
    def __init__(self, ...):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def _generate_json(self, prompt: str) -> str:
        client = await self._get_client()
        resp = await client.post(url, json=body)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
```

Benefits: connection reuse, proper async (no thread pool), retry via `httpx` transport, consistent with image service.

---

### 2.5 High — No Rate Limiting

**Problem:** Every endpoint is unauthenticated and unrate-limited. The `auth.py` module reads `x-user-id` but doesn't enforce it. Any client can call `/generate` unlimited times, consuming expensive Gemini API calls and Cloudflare image worker budget.

**Recommendation:** Add `slowapi` rate limiting middleware.

```python
# app/main.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# app/routers/generate.py
@router.post("/generate")
@limiter.limit("10/minute")
async def generate(request: Request, req: GenerateRequest): ...
```

Additionally, add API key authentication for production via a middleware or dependency.

---

### 2.6 High — `SlideData` Model is Overloaded

**Problem:** `SlideData` has 13 optional fields mixing concerns: layout rendering (`variant`, `blocks`, `layout`), AI generation (`image_prompt`, `image_query`, `visual_direction`, `chart_recommendation`), runtime enrichment (`chart_data`, `chart_audit`, `image_b64`), and content (`title`, `bullets`, `notes`). This makes the model hard to reason about and forces every layer to deal with fields it doesn't need.

**Recommendation:** Split into a layered model with explicit boundaries.

```python
class SlideContent(BaseModel):
    """Core content — what the AI generates and the user sees."""
    index: int
    title: str
    kicker: str | None = None
    subtitle: str | None = None
    bullets: list[str]
    notes: str

class SlideLayout(BaseModel):
    """Layout directives — how the PPTX engine renders this slide."""
    layout: str
    variant: SlideVariant | None = None
    blocks: list[dict] | None = None

class SlideEnrichment(BaseModel):
    """Runtime enrichment — images, charts, audits attached after generation."""
    chart_data: ChartData | None = None
    chart_audit: ChartAudit | None = None
    image_b64: str | None = None

class SlideAIHints(BaseModel):
    """AI generation hints — consumed by image/chart resolvers, not rendered."""
    visual_direction: str | None = None
    image_prompt: str | None = None
    image_query: str | None = None
    chart_recommendation: ChartRecommendation | None = None

class SlideData(BaseModel):
    content: SlideContent
    layout: SlideLayout
    enrichment: SlideEnrichment
    ai_hints: SlideAIHints
```

This is a larger refactor; it can be phased by adding the sub-models while keeping `SlideData` flat at first, then migrating consumers.

---

### 2.7 High — No Logging Infrastructure

**Problem:** Only `image_service.py` and `icons.py` use `logging.getLogger()`. The rest of the app uses `print()` or nothing. No structured logging, no request ID tracing, no correlation between generate/refine/export actions for the same session.

**Recommendation:** Add structured logging middleware and request ID tracing.

```python
# app/middleware/logging.py
import structlog
import uuid

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    with structlog.contextvars.bound_contextvars(request_id=request_id):
        logger = structlog.get_logger()
        logger.info("request_started", method=request.method, path=request.url.path)
        response = await call_next(request)
        logger.info("request_finished", status=response.status_code)
        response.headers["x-request-id"] = request_id
    return response
```

---

### 2.8 Medium — Audit Service is In-Memory Only

**Problem:** Same as session store — `AuditService._events` is a list in memory. Events are lost on restart, there's no query capability, and it grows unbounded.

**Recommendation:** Write audit events to a structured log sink (stdout as JSON for cloud, or a file for local dev) and optionally to a database for querying.

```python
class AuditService:
    def record(self, **kwargs) -> AuditEvent:
        event = AuditEvent(**kwargs, timestamp=datetime.now(timezone.utc))
        logger.info("audit_event", **event.model_dump())
        return event
```

For production, pipe stdout to a log aggregator (Cloud Logging, Datadog, etc.). Remove `get_events()` and `clear_events()` from the public API.

---

### 2.9 Medium — No Retry or Resilience for External API Calls

**Problem:** The Gemini API call and the Cloudflare image worker have no retry logic. A transient 503 or network blip results in an immediate error to the user. There's also no circuit breaker pattern.

**Recommendation:** Add retry with exponential backoff for idempotent external calls.

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=10),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
)
async def _generate_json(self, prompt: str) -> str:
    ...
```

For non-idempotent operations like `/refine`, only retry on connection errors (not on 4xx).

---

### 2.10 Medium — File Upload Security Gaps

**Problem:**
- `UploadService.save_upload()` only checks the file extension, not the actual content type (magic bytes). A file named `data.xlsx` containing malicious content would pass.
- No virus/malware scanning.
- No file size limit per user/session (only global limit).
- Uploaded files are stored on the local filesystem with predictable names (`{uuid}{suffix}`).

**Recommendation:**
1. Add magic byte validation for CSV and XLSX:
   - XLSX must start with `PK` (ZIP header)
   - CSV should be valid UTF-8
2. Consider scanning with `clamav` for production.
3. Rate-limit uploads per user.
4. Use `GCS` or `S3` for production uploads (already partially scaffolded via `STORAGE_PROVIDER`).

---

### 2.11 Medium — PPTX Engine is a God Class

**Problem:** `PptxEngine` inherits from `PptxLayoutMixin`, `PptxChartMixin`, and `PptxBlockMixin`. The layout mixin alone is 344 lines with 15+ methods. This makes the engine hard to test in isolation and hard to extend with new variants.

**Recommendation:** Refactor to a strategy/registry pattern for variants.

```python
class VariantRenderer(ABC):
    @abstractmethod
    def render(self, engine: PptxEngine, slide: Slide, data: SlideData) -> None: ...

class BigStatementRenderer(VariantRenderer): ...
class ThreePointsRenderer(VariantRenderer): ...

VARIANT_REGISTRY: dict[str, VariantRenderer] = {
    "big_statement": BigStatementRenderer(),
    "three_points": ThreePointsRenderer(),
    ...
}

class PptxEngine:
    def _apply_content_slide(self, slide, data):
        variant = self._variant_for(data)
        renderer = VARIANT_REGISTRY.get(variant, DefaultRenderer())
        renderer.render(self, slide, data)
```

This makes adding new variants trivial (just add a class + register it) and enables unit testing each variant independently.

---

### 2.12 Medium — No API Versioning Strategy

**Problem:** The API is prefixed with `/api/v1` but there's no mechanism to introduce v2 without breaking v1. The routers are directly mounted at the prefix.

**Recommendation:** Create a versioned router package.

```
app/routers/
├── v1/
│   ├── __init__.py      # FastAPI APIRouter with prefix="/api/v1"
│   ├── generate.py
│   ├── refine.py
│   ├── export.py
│   └── uploads.py
└── v2/                  # future
    └── ...
```

This ensures backward compatibility when evolving the API.

---

### 2.13 Low — Prompts Module is Empty

**Problem:** `app/prompts/__init__.py` is empty. All prompt templates are embedded as string literals in `gemini_api.py` (300+ lines of multiline f-strings). This makes prompts hard to review, iterate on, and version.

**Recommendation:** Extract prompts into the `app/prompts/` module as structured, testable templates.

```python
# app/prompts/generation.py
class GenerationPrompt:
    def __init__(self, req: GenerateRequest, upload_summary: dict | None):
        ...

    def render(self) -> str:
        return self._template.format(...)

# app/prompts/refinement.py
# app/prompts/chart_rules.py
# app/prompts/image_rules.py
```

This also enables prompt A/B testing in the future.

---

### 2.14 Low — Missing `.env` Validation at Startup

**Problem:** `Settings` has defaults for everything, so the app starts even with a completely empty `.env`. Invalid or missing production values (like `GEMINI_API_KEY` when `AI_PROVIDER=gemini`) only fail at request time.

**Recommendation:** Add startup validation in the lifespan.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_settings(settings)
    purge_local_temp_files()
    yield

def validate_settings(s: Settings) -> None:
    if s.ai_provider == "gemini" and not s.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
    if s.storage_provider == "gcs" and not s.gcs_bucket:
        raise RuntimeError("GCS_BUCKET is required when STORAGE_PROVIDER=gcs")
    ...
```

---

### 2.15 Low — No Health Check Depth

**Problem:** `/health` returns a static `{"status": "ok"}`. It doesn't actually check if any dependencies are available (Gemini API, file system, etc.).

**Recommendation:** Add a readiness check that probes actual dependencies.

```python
@router.get("/health")
async def health():
    checks = {
        "status": "ok",
        "version": "1.0.0",
        "storage": _check_storage_writable(),
        "session": _check_session_store(),
    }
    if settings.ai_provider == "gemini":
        checks["gemini"] = await _check_gemini_connectivity()
    if any(v == "error" for v in checks.values() if isinstance(v, str)):
        return JSONResponse(status_code=503, content=checks)
    return checks
```

---

### 2.16 Low — Test Infrastructure Gaps

**Problem:** Tests use `httpx.AsyncClient` with `ASGITransport` but there's no shared test client fixture. Each test file likely creates its own client. No test coverage reporting is configured.

**Recommendation:**
1. Add a shared `async_client` fixture in `conftest.py`.
2. Add `pytest-cov` to `pyproject.toml` and a `--cov` flag.
3. Add integration test for the full generate → refine → export flow.

---

## 3. Proposed Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI App                                                     │
│  ├── Middleware Stack                                             │
│  │   ├── CORS                                                    │
│  │   ├── Request ID + Structured Logging (structlog)            │
│  │   └── Rate Limiting (slowapi)                                 │
│  ├── Exception Handlers                                          │
│  │   └── SlideForgeError → structured JSON error                │
│  ├── Lifespan                                                    │
│  │   ├── Validate settings                                       │
│  │   ├── Initialize service singletons                           │
│  │   └── Purge expired temp files                                │
│  ├── /api/v1/health (liveness + readiness)                      │
│  ├── /api/v1/download/{filename}                                │
│  └── APIRouter v1                                                │
│      ├── POST /generate                                          │
│      ├── POST /refine                                            │
│      ├── POST /export                                            │
│      └── POST /uploads                                           │
└─────────────────────────────────────────────────────────────────┘

Dependencies (FastAPI Depends)
├── Settings (cached)
├── SessionService → SessionBackend (InMemory | Redis)
├── GeneratorService → GeminiService (mock) | GeminiApiService (httpx)
├── DlpService
├── AuditService (structured log sink)
├── StorageService (LocalFS | GCS)
├── UploadService
├── SlideImageResolver
└── SlideChartResolver

Service Layer (unchanged module structure, DI-injected)
├── generation/
│   ├── providers.py       → dependency functions
│   ├── gemini.py          → mock generator
│   ├── gemini_api.py      → httpx async client + tenacity retry
│   └── deck_normalizer.py
├── presentation/
│   ├── pptx_engine.py     → uses VariantRegistry
│   ├── pptx_canvas.py
│   ├── pptx_layout.py
│   ├── pptx_layouts.py    → refactored into variant renderers
│   ├── pptx_blocks.py
│   ├── pptx_charts.py
│   ├── pptx_text.py
│   ├── pptx_theme.py
│   ├── charts.py
│   ├── slide_charts.py
│   └── variants/          → new: individual variant renderers
│       ├── registry.py
│       ├── big_statement.py
│       ├── three_points.py
│       ├── split_image.py
│       └── ...
├── media/
│   ├── slide_images.py
│   ├── image_service.py
│   ├── image_prompts.py
│   └── icons.py
├── platform/
│   ├── auth.py            → FastAPI Security + OAuth2PasswordBearer (prod)
│   ├── dlp.py
│   ├── session.py         → SessionService + SessionBackend ABC
│   ├── storage.py         → StorageBackend ABC (LocalFS | GCS)
│   ├── uploads.py         → content-type validation
│   └── audit.py           → structured log writer
└── prompts/                → extracted prompt templates
    ├── generation.py
    ├── refinement.py
    ├── chart_rules.py
    └── image_rules.py
```

---

## 4. Implementation Phases

### Phase 1 — Stability & Developer Experience (1-2 weeks)

| # | Task | Priority | Effort |
|---|------|----------|--------|
| 1 | Structured error handling (`SlideForgeError` hierarchy + exception handler) | Critical | M |
| 2 | Startup settings validation | Low | S |
| 3 | Replace `urllib` with `httpx.AsyncClient` in `gemini_api.py` | High | M |
| 4 | Add `tenacity` retry to Gemini API + image service calls | Medium | S |
| 5 | Add request ID logging middleware + structlog | High | M |
| 6 | Add `slowapi` rate limiting to all POST endpoints | High | S |
| 7 | Enriched `/health` endpoint with dependency checks | Low | S |

### Phase 2 — Production Readiness (2-3 weeks)

| # | Task | Priority | Effort |
|---|------|----------|--------|
| 8 | Dependency injection via FastAPI `Depends()` for all services | Critical | L |
| 9 | `SessionBackend` ABC + `RedisSessionBackend` | Critical | M |
| 10 | `StorageBackend` ABC + `GCSStorageBackend` | Medium | M |
| 11 | Audit service → structured log sink (stdout JSON) | Medium | S |
| 12 | File upload magic-byte validation | Medium | S |
| 13 | Shared async test client fixture + pytest-cov | Low | M |
| 14 | Integration test: generate → refine → export | Low | M |

### Phase 3 — Architecture Refactoring (3-4 weeks)

| # | Task | Priority | Effort |
|---|------|----------|--------|
| 15 | Variant registry pattern for PPTX engine | Medium | L |
| 16 | Extract prompts into `app/prompts/` module | Low | M |
| 17 | Split `SlideData` into layered sub-models | High | L |
| 18 | API versioning via `app/routers/v1/` package | Medium | M |
| 19 | Auth middleware with API key enforcement for production | High | M |

---

## 5. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `SessionBackend` ABC over direct Redis | Allows local dev with in-memory, production with Redis, testing with mock — without changing service code |
| FastAPI `Depends()` over module-level singletons | Enables test overrides, explicit dependency graph, per-request lifecycle |
| `httpx.AsyncClient` over `urllib` | Native async, connection pooling, timeout control, consistent with existing `image_service.py` |
| Structured errors over raw `HTTPException` | Frontend can program against `error.code`, API is self-documenting, centralized logging |
| Variant registry over mixin inheritance | Open/closed principle: add variants without modifying engine, test each independently |
| Structlog over `logging` | Structured JSON logs for cloud aggregators, context binding for request tracing |
| `tenacity` retry + `httpx` timeouts | Resilience against transient API failures without custom retry loops |
| Rate limiting at middleware level | Protects all endpoints uniformly, prevents abuse before it hits service layer |

---

## 6. File Structure After Refactoring

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                   # App factory, middleware, exception handlers
│   ├── config.py                 # Settings (unchanged)
│   ├── dependencies.py           # FastAPI Depends providers (new)
│   ├── exceptions.py             # SlideForgeError hierarchy (new)
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── logging.py            # Request ID + structlog (new)
│   │   └── rate_limit.py         # slowapi config (new)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py            # SlideData (evolved, possibly layered)
│   │   └── session.py            # SessionData (new, from session.py)
│   ├── prompts/                  # Extracted templates (new)
│   │   ├── __init__.py
│   │   ├── generation.py
│   │   ├── refinement.py
│   │   ├── chart_rules.py
│   │   └── image_rules.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── v1/                   # Versioned routers (new)
│   │   │   ├── __init__.py
│   │   │   ├── generate.py
│   │   │   ├── refine.py
│   │   │   ├── export.py
│   │   │   └── uploads.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── generation/
│   │   │   ├── __init__.py
│   │   │   ├── providers.py      # → dependency functions
│   │   │   ├── gemini.py
│   │   │   ├── gemini_api.py     # → httpx client
│   │   │   └── deck_normalizer.py
│   │   ├── presentation/
│   │   │   ├── __init__.py
│   │   │   ├── pptx_engine.py
│   │   │   ├── pptx_canvas.py
│   │   │   ├── pptx_layout.py
│   │   │   ├── pptx_layouts.py   # → simplified, delegates to variants
│   │   │   ├── pptx_blocks.py
│   │   │   ├── pptx_charts.py
│   │   │   ├── pptx_text.py
│   │   │   ├── pptx_theme.py
│   │   │   ├── charts.py
│   │   │   ├── slide_charts.py
│   │   │   └── variants/         # Variant renderers (new)
│   │   │       ├── __init__.py
│   │   │       ├── registry.py
│   │   │       ├── big_statement.py
│   │   │       ├── three_points.py
│   │   │       └── ...
│   │   ├── media/
│   │   │   ├── __init__.py
│   │   │   ├── slide_images.py
│   │   │   ├── image_service.py
│   │   │   ├── image_prompts.py
│   │   │   └── icons.py
│   │   └── platform/
│   │       ├── __init__.py
│   │       ├── auth.py
│   │       ├── dlp.py
│   │       ├── session.py        # → SessionService + SessionBackend ABC
│   │       ├── storage.py        # → StorageBackend ABC
│   │       ├── uploads.py
│   │       └── audit.py          # → structured log writer
├── tests/
│   ├── conftest.py               # Shared fixtures (upgraded)
│   ├── test_api.py
│   ├── test_integration.py       # Full flow test (new)
│   └── ...
└── pyproject.toml
```

# SlideForge Project Setup Design

## Overview

Scaffold the SlideForge monorepo based on the PRD v1.0. The project is a Citigroup AI Presentation Generator powered by Gemini 1.5 Pro via Vertex AI that produces brand-compliant PPTX decks.

## Architecture

```
slide-creator/
├── apps/
│   ├── web/                    # React + TypeScript frontend
│   │   ├── src/
│   │   │   ├── components/     # UI components (shadcn/ui based)
│   │   │   │   ├── ui/         # shadcn/ui primitives
│   │   │   │   ├── layout/     # App shell, sidebar, header
│   │   │   │   ├── slides/     # Slide preview/editor components
│   │   │   │   └── create/     # Prompt input, deck type selector, file upload
│   │   │   ├── lib/            # Utilities, API client, cn() helper
│   │   │   ├── hooks/          # Custom React hooks
│   │   │   ├── pages/          # Route-level views
│   │   │   ├── styles/         # Citi theme tokens, globals.css
│   │   │   └── types/          # Shared TypeScript types
│   │   ├── tests/              # Vitest test files
│   │   ├── index.html
│   │   ├── vite.config.ts
│   │   ├── tailwind.config.ts
│   │   ├── tsconfig.json
│   │   ├── components.json     # shadcn/ui config
│   │   └── package.json
│   │
│   └── api/                    # FastAPI backend
│       ├── app/
│       │   ├── main.py         # FastAPI app entry, CORS, routes
│       │   ├── config.py       # Settings via pydantic-settings
│       │   ├── routers/
│       │   │   ├── generate.py  # POST /api/v1/generate
│       │   │   ├── refine.py   # POST /api/v1/refine
│       │   │   └── export.py   # POST /api/v1/export
│       │   ├── services/
│       │   │   ├── gemini.py   # Vertex AI Gemini client
│       │   │   ├── pptx_engine.py  # python-pptx template engine
│       │   │   ├── dlp.py      # DLP/compliance filter
│       │   │   └── storage.py  # GCS signed URL generation
│       │   ├── models/         # Pydantic request/response schemas
│       │   ├── templates/      # Citi .potx master template
│       │   ├── prompts/       # Gemini system prompts per deck type
│       │   └── tests/         # pytest test files
│       ├── pyproject.toml      # uv project config
│       └── Dockerfile
│
├── packages/
│   └── shared/                 # Shared types/constants (future)
│       └── package.json
│
├── pnpm-workspace.yaml
├── package.json                 # Root workspace scripts
├── turbo.json                   # Turborepo task pipeline
├── .gitignore
├── .env.example
├── PRD.html
└── README.md
```

## Frontend Stack (apps/web)

| Tool | Version | Purpose |
|------|---------|---------|
| React | 19.x | UI framework |
| TypeScript | 5.x | Type safety |
| Vite | 6.x | Build tool, dev server |
| Tailwind CSS | 4.x | Utility-first styling |
| shadcn/ui | latest | Component library, Citi-themed |
| React Router | 7.x | Client-side routing |
| TanStack Query | 5.x | Server state management |
| Vitest | 3.x | Unit testing |
| Playwright | latest | E2E testing (future) |

### Citi Theme Tokens

```
--citi-blue: #056DAE     (primary, headers, CTAs)
--citi-red: #E31837      (alerts, compliance flags)
--citi-gray: #F5F7FA     (backgrounds)
--citi-dark: #1E293B     (text)
Fonts: Arial, Calibri (PPTX); Inter (web UI)
```

shadcn/ui components will be customized with these tokens via `components.json` and Tailwind CSS variables.

### Frontend Pages (MVP)

1. **Login** - SSO redirect placeholder (Citi SSO integration is infrastructure-dependent)
2. **Create** - Prompt input (5000 char), deck type selector (Sales 9 / Internal 6), file upload (.xlsx/.csv)
3. **Preview** - Slide thumbnail grid, bullet editor per slide, refine actions ("Shorter", "More formal", "Add data")
4. **Export** - Download PPTX button, generation metadata display

## Backend Stack (apps/api)

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11 | Runtime |
| FastAPI | 0.115.x | API framework |
| uvicorn | 0.34.x | ASGI server |
| python-pptx | 1.x | PPTX generation |
| google-cloud-aiplatform | 1.x | Vertex AI / Gemini client |
| google-cloud-storage | 1.x | GCS signed URLs |
| google-cloud-dlp | 1.x | Data Loss Prevention |
| pydantic | 2.x | Schema validation |
| pydantic-settings | 2.x | Environment config |
| pytest | 8.x | Unit testing |
| httpx | 0.28.x | Async test client |

### API Endpoints (MVP)

```
POST /api/v1/generate   → Gemini → structured JSON → session store
POST /api/v1/refine     → Gemini with context → updated slide
POST /api/v1/export     → python-pptx render → signed URL (.pptx)
GET  /api/v1/health     → service readiness check
```

### Request/Response Schemas

```python
# Generate
class GenerateRequest(BaseModel):
    prompt: str = Field(max_length=5000)
    deck_type: Literal["sales_9", "internal_6"]
    file_id: str | None = None

class GenerateResponse(BaseModel):
    session_id: str
    slides: list[SlideData]

# Refine
class RefineRequest(BaseModel):
    session_id: str
    slide_index: int
    instruction: str

class RefineResponse(BaseModel):
    slide: SlideData

# Export
class ExportRequest(BaseModel):
    session_id: str

class ExportResponse(BaseModel):
    download_url: str
    expires_at: datetime

# SlideData
class SlideData(BaseModel):
    index: int
    title: str
    bullets: list[str]
    notes: str
    layout: str
    chart_data: dict | None = None
```

### Session Store (MVP)

In-memory dict with TTL (30 min auto-expiry). Keys are UUIDs. No persistent storage of prompts or content. Each session stores the full slide JSON between generate/refine/export calls.

### PPTX Template Engine

- Loads Citi master `.potx` template on startup
- Maps `SlideData.layout` to slide layouts in the master
- Applies Citi Blue (#056DAE) headers, Citi Red (#E31837) accents
- Fonts: Arial for headings, Calibri for body
- Auto-inserts "Confidential" footer + risk disclaimer on final slide
- Citi logo locked top-right, non-movable
- Chart rendering: bar, line, waterfall via python-pptx chart API

### DLP / Compliance Filter

- Pre-Gemini: Cloud DLP API scans prompt for MNPI, PII, account numbers
- Post-Gemini: Lexicon scan blocks prohibited terms ("guarantee returns", etc.)
- Gemini system prompt enforces Citi tone: "clear, professional, never guarantee returns"
- Flagged content triggers rewrite or rejection with user-facing message

## Development Tooling

| Tool | Purpose |
|------|---------|
| Turborepo | Task pipeline (build, lint, test, dev) |
| pnpm workspaces | Package management |
| ESLint + Prettier | Frontend linting/formatting |
| Ruff | Backend linting/formatting |
| uv | Python dependency management |
| .env files | Local config (API keys, project IDs) |

### Root Scripts (package.json)

```json
{
  "dev": "turbo dev",
  "build": "turbo build",
  "lint": "turbo lint",
  "test": "turbo test",
  "dev:web": "pnpm --filter web dev",
  "dev:api": "cd apps/api && uv run uvicorn app.main:app --reload",
  "test:web": "pnpm --filter web test",
  "test:api": "cd apps/api && uv run pytest"
}
```

## Data Flow

```
User → Frontend → POST /api/v1/generate
  → DLP scan (prompt)
  → Gemini 1.5 Pro (Vertex AI, us-central1)
  ← Structured JSON (slides)
  → Session store (in-memory, 30min TTL)

User → POST /api/v1/refine
  → DLP scan (instruction)
  → Gemini (with slide context)
  ← Updated slide JSON
  → Update session

User → POST /api/v1/export
  → python-pptx renders PPTX from session JSON + Citi template
  → Upload to GCS (temporary bucket)
  ← Signed URL (30min expiry)
  → Session auto-purge after 30 minutes
```

## Testing Strategy

### Frontend (Vitest)

- Component rendering tests for each page
- API client integration tests with MSW (Mock Service Worker)
- Citi theme token validation test

### Backend (pytest)

- `test_pptx_engine.py` - brand color validation, layout mapping, disclaimer insertion
- `test_gemini.py` - mock Gemini responses, verify JSON schema
- `test_dlp.py` - DLP blocking of prohibited terms
- `test_api.py` - httpx async test client for endpoint integration
- `test_session.py` - TTL expiry, session isolation

## Constraints

- No persistent storage of prompts or generated content
- All Gemini calls via Vertex AI (us-central1 or us-east4 only)
- API keys in GCP Secret Manager (local dev uses .env)
- PPTX files auto-deleted from GCS after 30 minutes
- English only for MVP
- Citi SSO integration deferred to infra phase; local dev uses mock auth

# SlideForge – Agent Guide

Two independent apps in this repo: `frontend/` and `backend/`. No monorepo orchestration.

## Root Commands

Run from project root:

| Command | Action |
|---------|--------|
| `make dev` | Start both backend (8000) and frontend (5173) |
| `make backend` | Start only backend |
| `make frontend` | Start only frontend |

## Frontend (`frontend/`)

- **Stack:** React 19 + Vite 8 + TypeScript 6 + Tailwind 4 + React Router 7 + TanStack Query 5
- **Package manager:** pnpm (v11). Lockfile: `frontend/pnpm-lock.yaml`
- **Path alias:** `@/` → `src/` (configured in both `vite.config.ts` and `tsconfig.app.json`)
- **Tailwind 4:** Uses `@import "tailwindcss"` in CSS (NOT `@tailwind` directives). Theme tokens defined via `@theme {}` block in `src/styles/globals.css`
- **TypeScript 6:** `noUnusedLocals`, `noUnusedParameters` enabled. `verbatimModuleSyntax` requires `import type` for type-only imports
- **Build:** `tsc -b && vite build` (two-step: typecheck then bundle)
- **Test:** `vitest` with `jsdom`, setup in `tests/setup.ts`. Globals enabled. Test files: `src/**/*.test.{ts,tsx}` and `tests/**/*.test.{ts,tsx}`
- **Dev server:** `pnpm dev` → port 5173. `VITE_API_URL` env var points API calls to `http://localhost:8000/api/v1`

### Commands (run from `frontend/`)

| Command | Action |
|---------|--------|
| `pnpm dev` | Dev server (port 5173) |
| `pnpm build` | Typecheck + production build |
| `pnpm test` | Vitest (run once) |
| `pnpm test:watch` | Vitest (watch) |
| `pnpm lint` | ESLint |

## Backend (`backend/`)

- **Stack:** FastAPI + Python 3.11 + uv package manager
- **Entry:** `app.main:app` (uvicorn)
- **API base:** `/api/v1` — endpoints: `uploads`, `generate`, `refine`, `export`, `health`
- **Test:** pytest with `asyncio_mode = auto`. Uses httpx `AsyncClient` + `ASGITransport`. Test env vars set in `tests/conftest.py`: `AI_PROVIDER=local`, `DLP_PROVIDER=local`, `STORAGE_PROVIDER=local`, no external API keys
- **Lint:** `ruff` replaces flake8/black. No isort or mypy configured.
- **Session store:** In-memory dict with 30-min TTL. No DB for MVP.

### Commands (run from `backend/`)

| Command | Action |
|---------|--------|
| `uv run uvicorn app.main:app --reload --reload-dir app` | Dev server (port 8000) |
| `uv run pytest` | Run all tests |
| `uv run pytest -v` | Verbose tests |
| `uv run ruff check app/ tests/` | Lint check |
| `uv run ruff check --fix app/ tests/` | Lint + auto-fix |

### Testing notes

- Backend: 20+ tests across 15 files in `backend/tests/`. Run from `backend/` dir.
- Frontend: 3 tests across 1 file. Run from `frontend/` dir.
- Test order: `ruff check → pytest` for backend, `tsc -b → vite build → vitest` for frontend.

## API endpoints

All under `/api/v1`:

- `POST /uploads` — Upload CSV/XLSX data → `{file_id}`
- `POST /generate` — `{prompt, deck_type, file_id?}` → `{session_id, slides[]}`
- `POST /refine` — `{session_id, slide_index, instruction}` → `{slide}`
- `POST /export` — `{session_id}` → `{download_url, expires_at}`
- `GET /health` — `{status, version}`

DLP pre-scan blocks prohibited terms (guarantee returns, risk-free, etc.) before generation.

## Brand tokens (Citi theme)

Defined in `frontend/src/styles/globals.css` as Tailwind `@theme` variables:
- `bg-citi-blue` / `text-citi-blue` (#056DAE)
- `bg-citi-red` / `text-citi-red` (#E31837)
- `bg-citi-gray` (#F5F7FA)
- `text-citi-dark` (#1E293B)

UI components: `Button`, `Card`, `Input` in `frontend/src/components/ui/`. `cn()` utility at `src/lib/utils.ts` (clsx + tailwind-merge).

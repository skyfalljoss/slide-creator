# SlideForge

SlideForge is a local web app for creating Citi-branded PowerPoint decks from a prompt and optional spreadsheet data. It includes a React frontend for the user workflow and a FastAPI backend for generation, refinement, compliance checks, uploads, and PPTX export.

## Features

- Generate a presentation from a written prompt.
- Choose between sales/client and internal deck formats.
- Upload CSV or XLSX data to guide slide content and charts.
- Preview generated slides before exporting.
- Refine individual slides with short instructions.
- Export the final deck as a PowerPoint file.
- Apply basic DLP/compliance checks before generation.

## Prerequisites

Install these before running the app:

- Python 3.11+
- `uv` for backend dependency management
- Node.js 20+
- `pnpm` 11+
- `make` for the root convenience commands

## First-Time Setup

Install backend dependencies:

```bash
cd backend
uv sync
```

Install frontend dependencies:

```bash
cd frontend
pnpm install
```

## Run The App

From the project root, start both servers:

```bash
make dev
```

This starts:

- Backend API: `http://localhost:8000/api/v1`
- Frontend app: `http://localhost:5173`

You can also run each server separately:

```bash
make backend
make frontend
```

If you run the frontend manually, start it from `frontend/`:

```bash
pnpm dev
```

If you run the backend manually, start it from `backend/`:

```bash
uv run uvicorn app.main:app --reload
```

## How To Use SlideForge

1. Open `http://localhost:5173` in your browser.
2. Go to the create flow.
3. Enter a clear prompt describing the deck you want.
4. Select the deck type.
5. Optionally upload a CSV or XLSX file with supporting data.
6. Generate the deck.
7. Review the slide preview.
8. Use a refinement option on any slide that needs changes.
9. Export the deck as PPTX.
10. Download the exported file before the link expires.

## Prompt Tips

Good prompts are specific about audience, purpose, and key points.

Example:

```text
Create a client-ready 9-slide sales deck for a regional banking product launch. Focus on market opportunity, client pain points, proposed solution, adoption plan, risks, and next steps.
```

Avoid putting sensitive client information, account numbers, emails, or restricted claims in prompts or uploads.

## Upload Files

Supported upload formats:

- `.csv`
- `.xlsx`

The backend parses uploaded data and can use it to inform generated slide content and charts. Keep uploads small and structured with clear column headers.

## Compliance Notes

SlideForge performs a pre-generation DLP scan. Generation may be blocked if the prompt or uploaded content contains prohibited or sensitive terms.

Examples of content to avoid:

- Personal email addresses
- Account-like identifiers
- Guarantees such as "risk-free" or "guaranteed returns"
- Confidential client data

If generation is blocked, revise the prompt or upload file to remove sensitive or prohibited content.

## Export Behavior

Exports are session-based and temporary.

- A generated deck is stored in the browser session.
- Export links expire after a short time.
- If you refine a slide after exporting, export again to get an updated PPTX.
- If an export link expires, create a new export from the export page.

## Useful Commands

Run these from the project root unless noted otherwise.

| Command | Purpose |
| --- | --- |
| `make dev` | Start backend and frontend together |
| `make backend` | Start only the backend server |
| `make frontend` | Start only the frontend server |
| `cd backend && uv run pytest` | Run backend tests |
| `cd backend && uv run ruff check app/ tests/` | Run backend lint |
| `cd frontend && pnpm test` | Run frontend tests |
| `cd frontend && pnpm lint` | Run frontend lint |
| `cd frontend && pnpm build` | Typecheck and build the frontend |

## Troubleshooting

### Frontend cannot reach the backend

Confirm the backend is running at `http://localhost:8000/api/v1`.

If needed, set the frontend API URL before starting Vite:

```bash
cd frontend
VITE_API_URL=http://localhost:8000/api/v1 pnpm dev
```

### Port already in use

The frontend uses port `5173`. The backend uses port `8000`. Stop the process using that port, then restart the app.

### Upload fails

Check that the file is a CSV or XLSX file and that it does not contain sensitive or prohibited content.

### Export link does not work

Export links expire. Return to the export page and generate a new PPTX export.

## Project Structure

```text
slide-creator/
  assets/     Shared static assets, including brand references
  backend/    FastAPI app, generation logic, uploads, exports, tests
  docs/       Design and implementation notes
  frontend/   React app, pages, UI components, API client, tests
  samples/    Example CSV/XLSX upload files for local testing
  Makefile    Root commands for running the app
```

## API Overview

All API routes are under `/api/v1`.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Health check |
| `POST /uploads` | Upload CSV/XLSX data |
| `POST /generate` | Generate a deck |
| `POST /refine` | Refine one slide |
| `POST /export` | Export a deck to PPTX |

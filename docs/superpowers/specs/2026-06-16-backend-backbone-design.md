# SlideForge Backend Backbone Design

## Overview

Implement the backend backbone for SlideForge from `PRD.html` using the existing FastAPI app under `backend/`. The goal is a production-shaped API that works locally without GCP credentials by default, while preserving clean seams for future Vertex AI, Cloud DLP, GCS, and Splunk adapters.

## Scope

In scope:

- Keep the existing frontend-facing API contract: `POST /api/v1/generate`, `POST /api/v1/refine`, `POST /api/v1/export`, and `GET /api/v1/health`.
- Add provider interfaces with deterministic local defaults for deck generation, DLP, export storage, and audit logging.
- Enforce prompt/refine validation, compliance scans, session TTL, PPTX rendering, and metadata-only audit events.
- Return usable local export URLs in development.

Out of scope for this backbone:

- Real Vertex AI calls.
- Real Cloud DLP inspection.
- Real GCS signed URLs.
- Splunk forwarding.
- Citi SSO and authorization.
- Long-term persistence.

## Architecture

The routers remain thin FastAPI orchestration layers. Business behavior lives in services with clear boundaries:

- `schemas.py` defines request and response payloads used by frontend and backend tests.
- `gemini.py` exposes a generator/refiner service with a local deterministic provider now and a future Vertex adapter seam.
- `dlp.py` scans prompt, refinement instruction, and generated slide text with local prohibited-term rules.
- `session.py` stores generated decks in memory and enforces TTL during reads and updates.
- `pptx_engine.py` renders Citi-branded `.pptx` bytes using `python-pptx`.
- `storage.py` stores local exports in a temp directory and returns a downloadable API URL; future GCS support can use the same interface.
- `audit.py` records metadata-only audit events without prompt, slide, or speaker-note content.

## Data Flow

Generate:

1. Validate `GenerateRequest`.
2. Scan prompt with DLP.
3. Generate deterministic PRD-aligned slides locally.
4. Scan generated slide text with DLP.
5. Create a TTL-bound session.
6. Emit metadata-only audit event.
7. Return `session_id` and slides.

Refine:

1. Validate `RefineRequest`.
2. Scan instruction with DLP.
3. Load session and target slide.
4. Refine the slide locally.
5. Scan refined slide text with DLP.
6. Update session.
7. Emit metadata-only audit event.
8. Return updated slide.

Export:

1. Load session.
2. Render PPTX bytes with Citi dimensions, colors, footer, and final disclaimer.
3. Store bytes locally by default.
4. Emit metadata-only audit event.
5. Return a `download_url` and `expires_at`.

## Error Handling

- Invalid request shape uses FastAPI/Pydantic `422` responses.
- DLP violations return `400` with the blocked terms.
- Missing or expired sessions return `404`.
- Missing slide indexes return `404`.
- Export/download misses return `404`.

## Testing

Backend tests cover:

- request validation and existing API contract;
- generation for `sales_9` and `internal_6`;
- prompt, instruction, and post-generation compliance blocking;
- TTL enforcement on session reads and updates;
- PPTX byte generation with final disclaimer;
- local storage/download URL behavior;
- audit event metadata excluding prompt and slide content.

Verification commands:

- `uv run ruff check app/ tests/`
- `uv run pytest`

## Decisions

- Use provider interfaces with local defaults first.
- Do not block implementation on cloud credentials or Citi infrastructure.
- Preserve frontend TypeScript types and endpoint paths.
- Keep content ephemeral in process memory and local temp export files for MVP development.

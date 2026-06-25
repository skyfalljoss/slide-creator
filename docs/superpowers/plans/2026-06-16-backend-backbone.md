# Backend Backbone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-shaped FastAPI backend backbone for SlideForge with local provider defaults and future GCP adapter seams.

**Architecture:** Preserve the existing API contract and keep routers thin. Move behavior into focused services for generation/refinement, DLP, session TTL, PPTX rendering, local storage, and metadata-only audit logging.

**Tech Stack:** FastAPI, Pydantic 2, pytest, httpx ASGITransport, python-pptx, uv, ruff.

---

## File Structure

- Modify: `backend/app/config.py` to add local provider settings and export directory config.
- Modify: `backend/app/models/schemas.py` to tighten validation and add typed chart/audit helper models only where useful.
- Modify: `backend/app/services/dlp.py` to centralize compliance scanning for plain text and slide collections.
- Modify: `backend/app/services/gemini.py` to provide deterministic local generation/refinement through a production-shaped service.
- Modify: `backend/app/services/session.py` to enforce TTL during reads and updates.
- Modify: `backend/app/services/pptx_engine.py` to render stronger Citi-branded PPTX output.
- Modify: `backend/app/services/storage.py` to write local export files and generate API download URLs.
- Create: `backend/app/services/audit.py` for metadata-only audit events.
- Modify: `backend/app/routers/generate.py`, `backend/app/routers/refine.py`, `backend/app/routers/export.py` to orchestrate the services.
- Modify: `backend/app/main.py` to expose local export download URLs.
- Modify/add tests under `backend/tests/` for the above behavior.

## Tasks

### Task 1: Validation, DLP, and Audit Tests

**Files:**
- Modify: `backend/tests/test_dlp.py`
- Modify: `backend/tests/test_api.py`
- Create: `backend/tests/test_audit.py`

- [ ] Add failing tests for instruction DLP, generated-slide DLP, and metadata-only audit events.
- [ ] Run `uv run pytest tests/test_dlp.py tests/test_audit.py tests/test_api.py -v` from `backend/` and confirm failures for missing audit service and stricter checks.
- [ ] Implement only enough service code in later tasks to satisfy these tests.

### Task 2: Settings and Schemas

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/models/schemas.py`

- [ ] Add settings: `ai_provider`, `dlp_provider`, `storage_provider`, `local_export_dir`, `api_base_url`, `audit_enabled`.
- [ ] Add request validation: prompt minimum length, instruction maximum length, and non-empty strings.
- [ ] Keep response shapes compatible with `frontend/src/types/index.ts`.
- [ ] Run `uv run pytest tests/test_api.py -v` from `backend/`.

### Task 3: Compliance Service

**Files:**
- Modify: `backend/app/services/dlp.py`

- [ ] Add `scan_text(text: str) -> list[str]` as the canonical scanner.
- [ ] Keep `scan_prompt` as a compatibility wrapper.
- [ ] Add `scan_slide(slide: SlideData) -> list[str]` and make `scan_slides` return flagged slide indexes using 1-based slide indexes.
- [ ] Run `uv run pytest tests/test_dlp.py -v` from `backend/`.

### Task 4: Session TTL Enforcement

**Files:**
- Modify: `backend/app/services/session.py`
- Modify: `backend/tests/test_session.py`

- [ ] Write a failing test proving `get_session` returns `None` after TTL expiry.
- [ ] Update `get_session` and `update_slide` to purge expired sessions before returning/updating.
- [ ] Run `uv run pytest tests/test_session.py -v` from `backend/`.

### Task 5: Local Generator Backbone

**Files:**
- Modify: `backend/app/services/gemini.py`
- Modify: `backend/tests/test_gemini.py`

- [ ] Add deterministic local deck structures that match PRD slide names for `sales_9` and `internal_6`.
- [ ] Make refinement preserve the same slide index/layout/chart data and update only title/bullets/notes.
- [ ] Run `uv run pytest tests/test_gemini.py -v` from `backend/`.

### Task 6: Audit Service

**Files:**
- Create: `backend/app/services/audit.py`
- Create/modify: `backend/tests/test_audit.py`

- [ ] Implement `AuditEvent` and `AuditService.record(...)` with metadata only: action, session_id, deck_type, slide_index, slide_count, timestamp.
- [ ] Add `clear_events()` and `get_events()` for tests.
- [ ] Ensure prompt text, bullet text, and notes are never accepted or stored by the audit API.
- [ ] Run `uv run pytest tests/test_audit.py -v` from `backend/`.

### Task 7: Router Orchestration

**Files:**
- Modify: `backend/app/routers/generate.py`
- Modify: `backend/app/routers/refine.py`
- Modify: `backend/app/routers/export.py`
- Modify: `backend/tests/test_api.py`

- [ ] Scan prompts before generation and scan generated slides before storing.
- [ ] Scan refine instructions before refinement and scan refined slide before updating.
- [ ] Record audit metadata for generate, refine, and export.
- [ ] Keep all endpoint paths and JSON response keys unchanged.
- [ ] Run `uv run pytest tests/test_api.py -v` from `backend/`.

### Task 8: PPTX and Local Storage Export

**Files:**
- Modify: `backend/app/services/pptx_engine.py`
- Modify: `backend/app/services/storage.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_pptx_engine.py`
- Modify: `backend/tests/test_api.py`

- [ ] Strengthen PPTX rendering with Citi slide dimensions, title/body textboxes when blank layouts are used, footer on every slide, and final disclaimer.
- [ ] Save local `.pptx` files under `local_export_dir`.
- [ ] Add `GET /api/v1/download/{filename}` for local downloads.
- [ ] Make `POST /export` return a local download URL and expiry timestamp.
- [ ] Run `uv run pytest tests/test_pptx_engine.py tests/test_api.py -v` from `backend/`.

### Task 9: Full Verification

**Files:**
- No new files.

- [ ] Run `uv run ruff check app/ tests/` from `backend/`.
- [ ] Run `uv run pytest` from `backend/`.
- [ ] If ruff or tests fail, fix the smallest relevant issue and rerun the failing command.

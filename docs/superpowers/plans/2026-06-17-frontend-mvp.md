# Frontend MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the SlideForge React frontend to the FastAPI backend for prompt generation, file upload, preview/refine, and PPTX export.

**Architecture:** Keep existing routes and Citi UI primitives. Add a small deck context persisted to `sessionStorage`, expand the typed API client, and replace mock page behavior with TanStack Query mutations and context updates.

**Tech Stack:** React 19, React Router 7, TanStack Query 5, TypeScript 6, Tailwind 4, Vitest, Testing Library.

---

## File Structure

- Modify: `frontend/src/types/index.ts` for upload/chart/deck state types.
- Modify: `frontend/src/lib/api.ts` for `uploadFile`, error normalization, and typed backend methods.
- Create: `frontend/src/state/DeckContext.tsx` for deck state, persistence, and helpers.
- Modify: `frontend/src/App.tsx` to wrap routes with `DeckProvider`.
- Modify: `frontend/src/pages/CreatePage.tsx` to upload files and call generate.
- Modify: `frontend/src/pages/PreviewPage.tsx` to render generated slides and call refine.
- Modify: `frontend/src/pages/ExportPage.tsx` to call export and render download metadata.
- Add tests near the relevant files.

## Tasks

### Task 1: API Client and Types

- [ ] Add tests for `uploadFile`, JSON methods, and backend error messages.
- [ ] Extend frontend types for upload responses, chart data, and deck state.
- [ ] Implement multipart upload and readable error handling.
- [ ] Run `pnpm test src/lib/api.test.ts`.

### Task 2: Deck State Provider

- [ ] Add tests for generated deck storage, slide updates, export result storage, and sessionStorage hydration.
- [ ] Implement `DeckProvider`, `useDeck`, and reducer-style helpers.
- [ ] Run `pnpm test src/state/DeckContext.test.tsx`.

### Task 3: Create Page Integration

- [ ] Add tests for prompt validation, upload+generate flow, and DLP error rendering.
- [ ] Replace fake navigation with upload/generate mutations.
- [ ] Store generated deck and navigate to `/preview`.
- [ ] Run relevant Create page tests.

### Task 4: Preview Page Integration

- [ ] Add tests for rendering context slides, redirect when missing deck, and refine updating a slide.
- [ ] Replace mock slides with deck context.
- [ ] Wire refine buttons to `/refine` and update context.
- [ ] Run relevant Preview page tests.

### Task 5: Export Page Integration

- [ ] Add tests for redirect without session, export call, and download link rendering.
- [ ] Replace fake export with `/export` mutation.
- [ ] Store export result and show expiry metadata.
- [ ] Run relevant Export page tests.

### Task 6: Full Frontend Verification

- [ ] Run `pnpm lint`.
- [ ] Run `pnpm test`.
- [ ] Run `pnpm build`.

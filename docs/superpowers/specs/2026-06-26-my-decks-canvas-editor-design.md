# My Decks Page + Canvas-Based PPTX Editor

**Date:** 2026-06-26
**Status:** Approved design — ready for implementation planning

## Problem

1. **No deck persistence:** Sessions live in memory with 30-min TTL. Decks vanish after that.
2. **No deck listing:** Sidebar has a "My Decks" nav link that's a dead link (no route, no page component).
3. **No in-browser editing:** The only way to modify a deck is through AI refine (`POST /refine`). Users can't manually edit title, bullets, notes, or layout before downloading.
4. **Export-only flow:** After generation, the only path is export. No way to save and revisit.

## Design

### 1. Backend: SQLite Deck Storage

**Table `decks`:**

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | UUID |
| `name` | TEXT | Deck name (from first slide title or user-set) |
| `deck_type` | TEXT | `sales_9` or `internal_6` |
| `theme` | TEXT | Theme name (e.g. `citi`) |
| `aspect_ratio` | TEXT | `16:9` or `4:3` |
| `slides` | TEXT (JSON) | Serialized `list[SlideData]` |
| `thumbnail_b64` | TEXT | Base64 PNG thumbnail of first slide. Generated on save by rendering the first slide to a small canvas (320x180) in the browser, then base64-encoding the result. |
| `created_at` | TEXT (ISO 8601) | Immutable |
| `updated_at` | TEXT (ISO 8601) | Updated on every save |

- Uses aiosqlite for async access. DB file at `backend/.data/decks.db`.
- No migrations framework needed — create table on first access if not exists.
- Module: `backend/app/services/platform/deck_store.py` — `DeckStore` class with async CRUD methods.
- DI provider: `get_deck_store()` in `dependencies.py`.

**New API endpoints (all under `/api/v1/decks`):**

| Method | Path | Action | Request | Response |
|---|---|---|---|---|
| `GET` | `/decks` | List all decks | Query: `?q=search&deck_type=sales_9&sort=newest` | `{decks: DeckSummary[]}` |
| `GET` | `/decks/{deck_id}` | Get full deck | — | `{id, name, deck_type, theme, aspect_ratio, slides[], thumbnail_b64, created_at, updated_at}` |
| `POST` | `/decks` | Save new deck | `{name, deck_type, theme, aspect_ratio, slides[], thumbnail_b64}` | `{id, name, created_at}` |
| `PUT` | `/decks/{deck_id}` | Update deck | `{name?, slides?}` | `{updated_at}` |
| `DELETE` | `/decks/{deck_id}` | Delete deck | — | `{ok: true}` |

`DeckSummary` (list response): `{id, name, deck_type, slide_count, thumbnail_b64, created_at, updated_at}` — excludes full `slides[]` payload for performance.

**Router file:** `backend/app/routers/decks.py` — registered in `main.py`.

### 2. Backend: Export Refactor

`POST /export` currently takes `session_id`. Extend to also accept `deck_id`:

- If `deck_id` provided: load slides from SQLite, render PPTX, return download URL
- If `session_id` provided: existing behavior (load from session store)
- Export still uses the existing `PptxEngine` with no changes

### 3. Frontend: My Decks Page (`/my-decks`)

**Route:** Added to `App.tsx` under `<Layout>`, replacing the catch-all redirect for this path.

**Page component:** `frontend/src/pages/MyDecksPage.tsx`

**Layout (3-column card grid):**
- **Header:** "My Decks" title + "+ New Deck" button (links to `/create`)
- **Search/filter bar:** Text search (filters by name), deck type dropdown, sort dropdown (Newest/Oldest/Name A-Z)
- **Card grid:** 3 columns, responsive
  - Each card: color-coded header (sales=blue, internal=red) with slide count icon, deck name, deck type label, date, action row (Edit → `/editor/:deckId`, Export → download PPTX, Delete → confirmation modal)
- **Empty state:** Illustration + "No decks yet" + "Create your first deck" CTA → `/create`
- **Pagination:** 12 per page if >12 decks exist

**API integration:** Uses TanStack Query (`useQuery` for list, `useMutation` for delete).

### 4. Frontend: Canvas Editor Page (`/editor/:deckId`)

**Route:** Added to `App.tsx` under `<Layout>`.

**Page component:** `frontend/src/pages/EditorPage.tsx`

**Layout (3-panel):**

**Left panel (180px) — Slide thumbnails:**
- Vertical list of slide thumbnails (title + mini-preview)
- Click to select slide → loads into canvas
- Drag-and-drop to reorder (HTML5 drag or `@dnd-kit/core`)
- "+ Add Slide" button below list — inserts a blank content slide (title="New Slide", no bullets, layout="content", variant=null) after the selected slide
- Delete icon on each thumbnail (with confirmation for last slide)

**Center panel — Fabric.js canvas:**
- Canvas size: 960×540px (16:9) or 960×720px (4:3) — scaled down if needed
- Gray workspace background around the slide
- Zoom controls: −/+ buttons, percentage display, "Fit" button
- Fabric.js configured with: undo/redo history (50 steps), selection controls, object serialization

**Right panel (260px) — Properties + Tools:**
- Section 1: **Slide Properties** (textarea/inputs)
  - Title, Subtitle/Kicker, Slide Layout (dropdown: all `SlideVariant` options), Bullet Points (editable list with add/remove), Speaker Notes (textarea)
  - Changes sync bidirectionally with canvas and auto-save
- Section 2: **Canvas Tools**
  - Add Text / Shape / Image / Line buttons
  - Font selector, Font Size selector, B/I/U toggles, color pickers
  - Delete selected object button
  - These operate on the Fabric.js canvas directly

**Header bar:**
- "← Back to My Decks" link
- Deck name (editable inline)
- "Slide X of Y" counter
- Undo / Redo buttons
- 💾 Save button (immediate save to API)
- ⬇ Export PPTX button (serialize canvas → PUT save → POST export → download)

### 5. Canvas ↔ SlideData Bridge

**Frontend library file:** `frontend/src/lib/canvas-bridge.ts`

**Rendering pipeline (SlideData → Fabric canvas):**
1. Clear canvas
2. Set background rect (theme color, 960×540)
3. Map each `SlideData` field to Fabric objects at preset positions:
   - `kicker` → `fabric.Textbox` at top, small uppercase, positioned (60, 40)
   - `title` → `fabric.Textbox`, large bold, positioned below kicker (60, 80)
   - `subtitle` → `fabric.Textbox`, medium, positioned below title
   - `bullets[]` → `fabric.Textbox` array, left-aligned with bullet prefix ("• "), positioned in content area
   - `blocks[]` → if present, rendered as structured groups (stats, tables, process)
   - `callout` → rendered as accent box if present
4. Mark all objects as initial state (for undo/redo baselining)

**Export pipeline (Fabric canvas → SlideData):**
1. Iterate all Fabric objects on canvas (excluding background)
2. Extract text content from `fabric.Textbox` objects
3. Map by position zone back to `SlideData` fields:
   - Top area → `kicker`
   - Title area → `title`
   - Middle area → `subtitle`
   - Content area → `bullets[]`
4. Preserve non-canvas fields: `notes`, `layout`, `chart_data`, `narrative_context` (from original SlideData)
5. Return updated `SlideData` object

**Auto-save:** Debounced 3 seconds after last canvas modification → call `exportFromCanvas()` → `PUT /decks/:deckId`. `fetch` with `AbortController` to cancel in-flight saves on new changes.

**Undo/Redo:** Fabric.js v6 built-in history via `canvas.undo()` / `canvas.redo()` with `history` option configured on initialization. Trackable changes: text edit, move, resize, add/delete object. 50-step history buffer.

### 6. Integration Points

**After generation (PreviewPage):**
- After viewing slides on PreviewPage, offer a "Save to My Decks" button in the header
- Calls `POST /decks` with current SlideData from DeckContext

**Export (EditorPage):**
- Export button: `exportFromCanvas()` → `PUT /decks/:id` to save latest → `POST /export` with `deck_id` → trigger download

**Existing ExportPage:**
- Unchanged — still exports via `session_id`. Added option to also work with `deck_id`.

**Sidebar:**
- "My Decks" nav link already exists (`/my-decks`) — now routes to the real page

### 7. Code Changes

| File | Changes |
|---|---|
| **Backend** | |
| `app/models/schemas.py` | Add `DeckSummary`, Deck response models |
| `app/services/platform/deck_store.py` | **New.** `DeckStore` class with async SQLite CRUD |
| `app/routers/decks.py` | **New.** 5 endpoints: GET list, GET one, POST create, PUT update, DELETE |
| `app/routers/export.py` | Extend to accept `deck_id` as alternative to `session_id` |
| `app/dependencies.py` | Add `get_deck_store()` DI provider |
| `app/main.py` | Register decks router, initialize DB on startup |
| **Frontend** | |
| `src/pages/MyDecksPage.tsx` | **New.** Deck list page with card grid |
| `src/pages/EditorPage.tsx` | **New.** Canvas editor page with 3-panel layout |
| `src/lib/canvas-bridge.ts` | **New.** SlideData ↔ Fabric.js bidirectional mapping |
| `src/lib/api.ts` | Add `listDecks()`, `getDeck()`, `saveDeck()`, `updateDeck()`, `deleteDeck()` |
| `src/types/index.ts` | Add `DeckSummary`, deck API types |
| `src/App.tsx` | Add `/my-decks` and `/editor/:deckId` routes |
| `src/components/layout/Sidebar.tsx` | Already has nav link — no changes needed |

**New frontend dependencies:**
- `fabric` (v6+) — Canvas library
- `@dnd-kit/core` / `@dnd-kit/sortable` — Drag-and-drop for slide reordering (optional: can use native HTML5 drag as lighter alternative)

### 8. Error Handling / Edge Cases

- **Canvas serialization fails:** Show error toast, do not save. Keep existing slide data.
- **Network down during auto-save:** Queue retry. Show "unsaved changes" indicator in header. Don't block editing.
- **Empty deck (0 slides after deleting all):** Prevent deletion of last slide. Minimum 1 slide.
- **Very long slide content (100+ bullets):** Canvas auto-sizes; properties panel scrolls.
- **Concurrent edits (same deck in two tabs):** Last-write-wins. Acceptable for MVP.
- **Deck not found (editor loaded with deleted ID):** Show 404 state with "Back to My Decks" link.
- **Navigation away with unsaved changes:** Browser `beforeunload` event warns user.
- **JSON parse errors loading malformed deck:** Show error state, offer to delete corrupted deck.

### 9. Out of Scope (Deferred)

- Multi-user support (single-user for MVP, user_id column added later)
- Slide templates / copy from template
- AI-assisted image generation on canvas
- Real-time collaboration
- Version history / diff
- Animation / transitions in editor
- Mobile-responsive editor (desktop-focused)
- PPTX import (import existing .pptx to edit)

### 10. Styling

Follows existing Citi theme tokens from `globals.css`:
- `bg-citi-blue` (#056DAE) — Sales deck cards, primary buttons, selected slide border
- `bg-citi-red` (#E31837) — Internal deck cards, delete actions, accent
- `bg-citi-gray` (#F5F7FA) — Panel backgrounds, empty states
- `text-citi-dark` (#1E293B) — Primary text, editor header bar
- Use existing `Button`, `Card`, `Input` UI components where applicable

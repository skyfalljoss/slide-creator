# Native PPTX Editing with ONLYOFFICE

**Date:** 2026-06-26  
**Status:** Approved design

## Goal

Replace the custom form-based deck editor with native in-browser PPTX editing through self-hosted ONLYOFFICE Docs Community Edition. Every generated deck must be persisted as a PPTX before the editor opens or a download becomes available. Each successful save creates an immutable file version, and the latest five versions remain recoverable.

This feature is for an internal deployment with fewer than ten concurrent editors. ONLYOFFICE Community Edition's AGPLv3 license is acceptable for this use.

## User Experience

### Creation flow

1. The user submits a deck-generation request.
2. The backend generates structured slide data and renders a PPTX.
3. The backend validates the PPTX, stores it as version 1, and creates the deck record.
4. Only after persistence succeeds does the frontend navigate to `/editor/:deckId`.
5. The editor opens the stored PPTX in ONLYOFFICE Presentation Editor.

The current Preview page remains temporarily for route compatibility but is not part of the normal creation flow.

### Editor page

The editor is a focused full-screen page rather than the current three-panel custom editor.

- A thin SlideForge header contains Back to My Decks, an editable deck name, save status, version history, and Download.
- ONLYOFFICE occupies the remaining viewport and provides slide thumbnails, text and object editing, formatting, notes, layouts, images, charts, and slide reordering.
- ONLYOFFICE's Save action uses force-save.
- The SlideForge status progresses through `Unsaved`, `Saving`, and `Saved as version N`.
- Download is disabled while a save is pending and always returns the current persisted version.
- A save failure leaves the previous current version intact and presents Retry.
- Restoring an older version creates a new version from it; history is not rewritten.

### My Decks

- Edit opens `/editor/:deckId` with the current PPTX version.
- Download returns the current stored PPTX directly.
- Deck cards continue to use deck metadata and a preview derived from the current PPTX.

## Source of Truth

The persisted PPTX is the authoritative editable and downloadable deck. Structured slide JSON remains generation provenance and may support future AI workflows, but it is not synchronized from arbitrary ONLYOFFICE edits and must not be used to regenerate downloads after native editing begins.

## Data Model

Use PostgreSQL for deck and version metadata. Store PPTX bytes in Google Cloud Storage rather than as database BLOBs.

### `decks`

| Column | Purpose |
|---|---|
| `id` | Stable UUID primary key |
| `name` | User-visible deck name |
| `owner_id` | Internal user identity |
| `current_version_id` | Foreign key to the active `deck_versions` row |
| `generation_payload` | Optional JSON generation provenance |
| `created_at` | Creation timestamp |
| `updated_at` | Last metadata or version change timestamp |

### `deck_versions`

| Column | Purpose |
|---|---|
| `id` | UUID primary key |
| `deck_id` | Parent deck foreign key |
| `version_number` | Monotonically increasing number per deck |
| `storage_key` | Immutable GCS object path |
| `sha256` | Integrity and deduplication checksum |
| `size_bytes` | Stored file size |
| `source` | `generated`, `onlyoffice_save`, or `restore` |
| `created_by` | Internal user or service identity |
| `created_at` | Version timestamp |

The active version is selected through `decks.current_version_id`. A successful commit retains the newest five versions. Older database rows and objects are removed only after the new version and current-version pointer commit successfully. Cleanup is retryable and must never invalidate the current version.

## Backend Components

### Deck generation service

The generation service renders and validates the initial PPTX, uploads an immutable version-1 object, and creates the deck and version rows in a transaction. Navigation to the editor is permitted only after this operation succeeds.

### Deck file service

This service owns version creation, current-version reads, restores, retention, checksums, and file validation. Storage access remains behind the existing storage abstraction, extended with durable versioned objects and reads.

### ONLYOFFICE integration service

This service creates JWT-signed editor configurations containing:

- a stable deck and version identity;
- a unique document key for the current persisted version;
- a short-lived URL from which ONLYOFFICE can fetch the PPTX;
- the authenticated save callback URL;
- presentation edit mode and force-save enabled;
- the current user identity and display name.

The document key remains stable during one editing session. A newly opened session uses a new key derived from the new current version so ONLYOFFICE does not reuse stale content.

### Save callback

The callback handles ONLYOFFICE status `6` for force-save and status `2` when an editing session closes with changes.

For a save-bearing callback, the backend:

1. Validates the ONLYOFFICE JWT and expected document identity.
2. Accepts the edited-file URL only from the configured ONLYOFFICE host.
3. Downloads with strict timeout and maximum-size limits.
4. Validates ZIP/OpenXML structure and confirms at least one slide exists.
5. Computes SHA-256 and applies idempotency using callback identity plus checksum.
6. Uploads a new immutable GCS object.
7. Inserts the next version and updates `current_version_id` atomically.
8. Returns `{"error": 0}` to ONLYOFFICE.
9. Schedules retention cleanup after the commit.

If validation, upload, or database commit fails, the current version remains unchanged. The callback returns the appropriate ONLYOFFICE error response, records structured diagnostics, and allows a retry.

## API Surface

All routes remain under `/api/v1`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/generate` | Generate, persist version 1, and return `deck_id` plus editor destination |
| `GET` | `/decks/{deck_id}/editor-config` | Return a short-lived JWT-signed ONLYOFFICE configuration |
| `GET` | `/decks/{deck_id}/content` | Stream the authorized current or specified version to ONLYOFFICE |
| `POST` | `/decks/{deck_id}/onlyoffice/callback` | Receive save and close callbacks |
| `GET` | `/decks/{deck_id}/versions` | List the retained versions |
| `POST` | `/decks/{deck_id}/versions/{version_id}/restore` | Restore by creating a new current version |
| `GET` | `/decks/{deck_id}/download` | Download the current persisted PPTX |
| `PATCH` | `/decks/{deck_id}` | Rename the deck |

The generation response no longer relies on an expiring session for the primary user flow. Legacy session-based export may remain during migration but must not be used by the new editor or My Decks download actions.

## Frontend Components

### `EditorPage`

`EditorPage` loads deck metadata and editor configuration, injects the ONLYOFFICE Docs API script from the configured document-server URL, and creates the presentation editor. It does not parse or reconstruct PPTX content.

The editor reports state changes to the header. After force-save, the frontend waits for backend confirmation that a new version is current before showing `Saved as version N` or enabling Download. Polling the deck/version status is sufficient for the internal MVP; a WebSocket is not required.

The page warns before navigation while ONLYOFFICE reports unsaved changes or a save confirmation is pending. It disposes the editor instance when unmounted.

### Version history

A compact header dialog lists version number, creation time, source, and creator for the retained versions. Restore requires confirmation and refreshes the ONLYOFFICE editor using the newly created current version.

### Configuration

Frontend and backend receive the public/internal ONLYOFFICE URL through environment configuration. The backend separately uses an internal document-server URL where appropriate for server-to-server calls.

## Security

- Serve SlideForge and ONLYOFFICE over HTTPS on internal DNS reachable through the corporate network or VPN.
- Sign editor configuration and callbacks with a dedicated ONLYOFFICE JWT secret stored in Secret Manager.
- Scope file access tokens to one deck/version and a short expiry.
- Verify deck ownership or internal authorization on every metadata, content, history, restore, and download route.
- Restrict callback file downloads to the configured ONLYOFFICE origin to prevent server-side request forgery.
- Enforce content type, maximum file size, ZIP/OpenXML validation, and malware scanning when the production scanning service is available.
- Do not expose GCS objects publicly.
- Log version IDs and deck IDs, but never JWTs, signed URLs, or document content.

## Failure Handling

- **Initial render or persistence fails:** no deck is presented as editable; the Create page shows a retryable generation error.
- **ONLYOFFICE unavailable:** the editor displays a service-unavailable state with Back and Retry; existing PPTX downloads remain available.
- **Save callback fails:** keep the old current version, show Save failed, and allow force-save retry.
- **Duplicate callback:** return success for the already persisted checksum without creating another version.
- **Concurrent saves:** allocate version numbers transactionally and use optimistic current-version checks. Conflicting complete files create distinct versions; the latest successful save becomes current and is auditable.
- **Corrupt or oversized file:** reject it, retain the previous current version, and emit an audit event.
- **GCS cleanup fails:** retain extra old versions temporarily and retry cleanup; never fail the completed save.
- **Database unavailable:** do not upload a user-visible current version. Orphan uploads are tagged and removed by a scheduled cleanup job.

## Deployment

The internal MVP runs on one GCP Compute Engine VM using Docker Compose:

- Nginx terminates HTTPS and routes the React app, FastAPI API, and ONLYOFFICE endpoints.
- React is served as static assets.
- FastAPI handles application APIs, file authorization, and callbacks.
- ONLYOFFICE Docs Community Edition provides native PPTX editing.
- PostgreSQL stores deck and version metadata.
- Google Cloud Storage stores immutable PPTX objects.

Start with 4 vCPU, 16 GB RAM, and a persistent disk. The official ONLYOFFICE baseline requires at least 4 GB RAM and substantial local disk; the larger VM leaves capacity for the application services and fewer than ten concurrent editors.

Use health checks for Nginx, FastAPI, PostgreSQL, and ONLYOFFICE. Back up PostgreSQL nightly. GCS object versioning is application-managed, and lifecycle rules remove tagged orphan objects. The architecture can later separate PostgreSQL, FastAPI, and ONLYOFFICE without changing the file/version API contracts.

Kubernetes and Cloud Run are intentionally excluded for the initial ONLYOFFICE deployment. They add operational complexity or do not match ONLYOFFICE's persistent, stateful runtime needs at this scale.

## Local Development

Provide Docker Compose services for PostgreSQL and ONLYOFFICE alongside the existing independent frontend and backend development commands. A local file-storage adapter mirrors immutable GCS object behavior. Both the browser-facing document URL and callback URL must be reachable from the ONLYOFFICE container; container hostnames must not be confused with browser hostnames.

Tests may use mocked callbacks and storage for speed. A separate opt-in smoke profile starts the real ONLYOFFICE container.

## Testing

### Backend unit tests

- Initial version creation and atomic current-version selection.
- Monotonic version allocation, five-version retention, and restore-as-new-version.
- Callback JWT, status, origin, timeout, size, PPTX structure, and checksum validation.
- Callback idempotency and concurrent-save behavior.
- Failure behavior for storage, database, and cleanup errors.
- Authorization on content, version, restore, and download routes.

### Backend integration tests

- Generate to persisted version 1.
- Editor configuration references the persisted current version.
- Simulated ONLYOFFICE callback creates version 2.
- Download returns byte-for-byte content from version 2.
- Restore creates a new version and updates the current pointer.

### Frontend tests

- Successful editor bootstrap and teardown.
- Loading and service-unavailable states.
- `Unsaved`, `Saving`, `Saved`, and `Save failed` header states.
- Download disabled while save confirmation is pending.
- Version listing, restore confirmation, and editor refresh.
- Navigation warning while unsaved or pending.

### Deployment smoke test

An opt-in Docker Compose smoke test starts a real ONLYOFFICE container, opens a generated PPTX, submits a force-save callback, and verifies that the stored result is a readable PPTX. Production health checks verify document-server reachability and callback connectivity.

## Migration

1. Add PostgreSQL deck/version tables and the durable storage methods without removing current SQLite/session paths.
2. Generate and persist version 1 during deck creation.
3. Add ONLYOFFICE configuration, content, callback, history, restore, and direct-download APIs.
4. Replace the current custom `EditorPage` with the ONLYOFFICE host page.
5. Route successful generation directly to the editor.
6. Change My Decks download to serve the current persisted PPTX.
7. Keep legacy Preview and session export temporarily, then remove them after existing flows and data are migrated.

## Out of Scope

- External or commercial SaaS licensing.
- More than ten concurrent editors or clustered ONLYOFFICE.
- Real-time collaboration features beyond those provided by ONLYOFFICE.
- Synchronizing arbitrary native PPTX edits back into SlideForge's structured slide JSON.
- Kubernetes deployment.
- More than five retained application versions.
- Mobile editor optimization.

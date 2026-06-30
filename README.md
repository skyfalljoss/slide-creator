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
uv run uvicorn app.main:app --reload --reload-dir app
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
| `make stack-up` | Build and start the internal Docker stack |
| `make stack-down` | Stop the stack without deleting durable volumes |
| `make stack-logs` | Follow application and editor logs |
| `make migrate` | Apply migrations in a one-off backend container |
| `make backup` | Back up PostgreSQL to the configured GCS URI |
| `make onlyoffice-shutdown` | Prepare ONLYOFFICE for a graceful stop |
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

## Internal Docker Deployment

The production-shaped Compose stack runs PostgreSQL 16, the FastAPI backend,
ONLYOFFICE Docs Community 9.4, and the Nginx-served frontend on one VM. Only
Nginx publishes a host port. PostgreSQL, the backend, and ONLYOFFICE remain on
the private Compose network.

For a small internal deployment (fewer than ten concurrent users), start with
an 8 GB RAM VM plus swap and monitor memory, swap pressure, and CPU during real
editing sessions. ONLYOFFICE also has a 2 GB shared-memory allocation, so keep
headroom for the host instead of sizing only to the Compose memory limits.
Adjust limits only after measuring usage.

### Configure and start

1. Install Docker Engine, the Compose plugin, and Google Cloud CLI on the VM.
2. Copy `.env.example` to `.env`.
3. Generate separate secrets instead of using the example values:

   ```bash
   openssl rand -base64 32
   openssl rand -base64 32
   ```

   Store one result in `POSTGRES_PASSWORD` and the other in
   `ONLYOFFICE_JWT_SECRET`. Never commit `.env`; it is ignored by Git.

4. Set `PUBLIC_APP_URL` to the browser-visible origin and
   `ONLYOFFICE_PUBLIC_URL` to the same origin plus `/onlyoffice`, for example
   `https://slides.internal.example/onlyoffice`. Provision the internal DNS
   record first.
5. Keep the deployment default `STORAGE_PROVIDER=gcs` and set real
   `GCP_PROJECT_ID` and `GCS_BUCKET` values. Grant the GCE VM service account
   object read/write/delete access to that private bucket instead of placing a
   service-account key in `.env`. Enable bucket object versioning with a
   lifecycle for noncurrent objects as a second recovery layer. The local
   `deck-files` volume is for development only: a PostgreSQL backup does not
   contain those PPTX files.
6. Validate and start:

   ```bash
   docker compose --env-file .env config --quiet
   make stack-up
   docker compose ps
   curl --fail http://127.0.0.1/healthz
   ```

The backend container applies Alembic migrations before Uvicorn starts. A
migration failure therefore stops that container instead of serving against an
old schema. Stack and migration Make targets pass `.env` explicitly; the
backup target exports that same file for the host-side upload script.

ONLYOFFICE is pinned to `onlyoffice/documentserver:9.4.0.1` and uses JWT on
every editor request. Its document fetches target the backend's private
`http://backend:8000` origin, so `ALLOW_PRIVATE_IP_ADDRESS=true` is required;
the service is deliberately not published on the VM. Nginx removes the
`/onlyoffice/` prefix when proxying and forwards its external virtual path and
WebSocket headers. The editor's Data, logs, application library, and bundled
database paths use named volumes so container replacement does not discard
state.

Content links expire after five minutes. Callback links default to seven days
through `ONLYOFFICE_CALLBACK_TOKEN_TTL_SECONDS=604800`, while ONLYOFFICE's
signed callback body authorization remains mandatory. An editor left open for
more than seven days must be reloaded before saving.

Terminate HTTPS at an internal load balancer or trusted reverse proxy before
production use. Forward the original host and protocol to this stack, restrict
the VM firewall to that proxy and administrative access, and do not expose the
ONLYOFFICE container directly. Set the outer load balancer's request timeout to
at least 600 seconds so it does not terminate a generation request before
Nginx's bounded API timeout.

Before an image upgrade, VM reboot, or planned stack stop, run
`make onlyoffice-shutdown`. `make stack-down` runs this automatically and waits
up to five minutes for `documentserver-prepare4shutdown.sh` before stopping
containers. If graceful preparation fails, inspect ONLYOFFICE logs before
choosing an explicit forced `docker compose --env-file .env down`.

### Nightly database backups

Set `BACKUP_GCS_URI` to a private `gs://` prefix. The backup script streams
`pg_dump` from PostgreSQL, compresses it into a permission-restricted temporary
file, uploads it with `gcloud storage`, and always removes the temporary file.
The VM identity needs object-creation permission on the backup bucket. The
script refuses to call a PostgreSQL-only backup complete when
`STORAGE_PROVIDER=local`; `ALLOW_INCOMPLETE_LOCAL_BACKUP=true` is an explicit
development-only acknowledgement that local PPTX files are omitted.

Install `/etc/systemd/system/slideforge-backup.service`:

```ini
[Unit]
Description=Back up SlideForge PostgreSQL to GCS
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
User=slideforge
WorkingDirectory=/opt/slideforge
EnvironmentFile=/opt/slideforge/.env
ExecStart=/opt/slideforge/deploy/backup-postgres.sh
```

Install `/etc/systemd/system/slideforge-backup.timer`:

```ini
[Unit]
Description=Run the SlideForge backup nightly

[Timer]
OnCalendar=*-*-* 02:00:00 UTC
Persistent=true
RandomizedDelaySec=15m

[Install]
WantedBy=timers.target
```

Enable it with:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now slideforge-backup.timer
sudo systemctl list-timers slideforge-backup.timer
```

### Restore drill

Run this drill regularly against a disposable database, never the live
`slideforge` database. The restore script accepts only a constrained drill
database name, requires an exact confirmation, checks gzip integrity, refuses
to overwrite an existing database, and uses a transaction with psql
`ON_ERROR_STOP`:

```bash
RESTORE_CONFIRM_TARGET=slideforge_restore \
  ./deploy/restore-postgres.sh \
  gs://BUCKET/PREFIX/slideforge-TIMESTAMP.sql.gz \
  slideforge_restore
docker compose --env-file .env exec -T postgres \
  psql -U slideforge -d slideforge_restore \
  -c 'SELECT count(*) FROM decks;'
docker compose --env-file .env exec -T postgres \
  dropdb -U slideforge slideforge_restore
```

If a drill fails, retain the command output, correct the backup or permission
problem, and repeat the drill before treating backups as recoverable.

### Legacy deck migration and orphan cleanup

Back up both databases and deck object storage before migration. The importer
reads the legacy SQLite database without modifying it, preserves deck IDs and
timestamps, renders an authoritative version-1 PPTX, and skips IDs already in
the versioned database. It continues after individual bad rows but exits
nonzero when any row fails:

```bash
cd backend
uv run python scripts/migrate_sqlite_decks.py \
  --sqlite-path .data/decks.db \
  --owner-id local-user
```

The importer has conservative file, row-JSON, nesting, and slide-count limits.
Use `--help` to inspect the override flags before increasing a limit for a
trusted legacy database.

Inspect orphan candidates before deletion. Cleanup compares storage against
all version rows across owners and protects files modified within the last 24
hours. Dry-run is the default; deletion requires the explicit `--apply` flag:

```bash
cd backend
uv run python scripts/cleanup_orphan_deck_files.py --dry-run
uv run python scripts/cleanup_orphan_deck_files.py --apply
```

Run the opt-in persistence and editor save-flow checks against disposable
integration infrastructure. They are strictly skipped when their environment
variables are absent:

```bash
cd backend
TEST_DATABASE_URL=postgresql+asyncpg://slideforge:slideforge@localhost:5432/slideforge \
  uv run pytest -m postgres -v
ONLYOFFICE_SMOKE_URL=http://localhost:8080 \
ONLYOFFICE_SMOKE_JWT_SECRET="$ONLYOFFICE_JWT_SECRET" \
ONLYOFFICE_SMOKE_FIXTURE_HOST=host.docker.internal \
  uv run pytest -m onlyoffice -v
```

`ONLYOFFICE_SMOKE_FIXTURE_HOST` must resolve from the Document Server to the
machine running pytest. The smoke test uses the signed conversion service, so
it fails if ONLYOFFICE cannot fetch or process the fixture PPTX.

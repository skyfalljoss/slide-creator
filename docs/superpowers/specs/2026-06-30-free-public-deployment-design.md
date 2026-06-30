# Free Public Deployment Design

**Date:** 2026-06-30

**Status:** Approved in conversation

## Goal

Publish SlideForge on the public internet without a recurring infrastructure
charge, while preserving the current React, FastAPI, PostgreSQL, and ONLYOFFICE
architecture.

## Target Environment

The deployment uses one Oracle Cloud Infrastructure Always Free Ampere A1 VM
running Ubuntu. Allocate 4 ARM OCPUs and 24 GB RAM when free-tier capacity is
available. The VM runs the repository's existing Docker Compose stack. The
pinned PostgreSQL, Nginx, Python, Node, and ONLYOFFICE 9.4.0.1 images all provide
ARM64 builds.

This target is intended for a personal demonstration or a small, low-traffic
deployment. Oracle may have no free A1 capacity in a selected region, and the
free tier does not provide a production availability guarantee.

## Public Network and TLS

A free DuckDNS hostname points to the VM's reserved public IP. Oracle's network
security list and the Ubuntu firewall allow inbound TCP 22, 80, and 443 only.
SSH uses public-key authentication.

Caddy runs on the host and obtains and renews a public TLS certificate. The
Compose `web` service binds to `127.0.0.1:8080`, so application traffic cannot
bypass Caddy. Caddy redirects HTTP to HTTPS and proxies HTTPS requests to the
local Nginx container. Nginx continues to route `/api/` to FastAPI and
`/onlyoffice/` to ONLYOFFICE.

The browser-visible values use the same HTTPS origin:

```dotenv
PUBLIC_APP_URL=https://SLUG.duckdns.org
ONLYOFFICE_PUBLIC_URL=https://SLUG.duckdns.org/onlyoffice
WEB_PORT=127.0.0.1:8080
```

## Application Services

The existing `compose.yaml` starts four services:

- `web`: the built React application and internal Nginx reverse proxy.
- `backend`: FastAPI, with Alembic migrations applied before startup.
- `postgres`: durable deck metadata and versions.
- `onlyoffice`: browser-based PowerPoint editing with JWT validation.

Only host Caddy is publicly reachable. PostgreSQL, FastAPI, and ONLYOFFICE stay
on the private Compose network.

## Free-Tier Configuration

Set `STORAGE_PROVIDER=local` so deck PPTX files use the persistent Docker
`deck-files` volume instead of paid object storage. `GCP_PROJECT_ID` and
`GCS_BUCKET` receive harmless placeholder values because the current Compose
file requires them during interpolation even when GCS is disabled.

Set `AI_PROVIDER=local` and leave `GEMINI_API_KEY` empty. This avoids API
charges but uses the application's deterministic local generation behavior.
Enabling Gemini later requires a key and may incur provider charges.

Generate independent random values for `POSTGRES_PASSWORD` and
`ONLYOFFICE_JWT_SECRET`. The deployment `.env` remains only on the VM, has mode
`600`, and is never committed.

## Persistence and Backups

Docker named volumes preserve PostgreSQL, deck files, and ONLYOFFICE state
across container replacement and VM restart. The deployment guide includes a
nightly local `pg_dump` job and a deck-volume archive stored under a
root-readable backup directory on the same VM.

Same-VM backups protect against accidental application data changes but not VM,
boot-volume, account, or regional failure. A deployment containing important
data must copy encrypted backups to a different machine or object store. That
off-host copy is outside the strictly free baseline because free storage quotas
and retention policies can change.

## Deployment and Upgrade Flow

Initial deployment installs Docker Engine, the Compose plugin, Git, and Caddy;
clones the repository; writes `.env`; validates the Compose model; and starts
the stack. Health checks must pass before DNS traffic is considered live.

An upgrade performs these actions in order:

1. Create and verify a backup.
2. Gracefully prepare ONLYOFFICE for shutdown.
3. Fetch the intended Git revision.
4. Rebuild and restart the Compose stack.
5. Confirm container health and exercise generation, editing, and export.

Rollback checks out the previously recorded Git revision and rebuilds the
containers. Database migrations require restore from the pre-upgrade backup if
the older application revision cannot read the upgraded schema.

## Verification

The deployment is accepted only when all of these checks succeed:

- Caddy serves the DuckDNS hostname over trusted HTTPS and redirects HTTP.
- `/healthz` and `/api/v1/health` return successful responses.
- All four Compose services report healthy or running as appropriate.
- A user can generate a deck, open it in ONLYOFFICE, save a change, and export
  the resulting PPTX.
- Deck metadata and files remain available after a controlled VM reboot.
- A database backup passes gzip integrity checking and can be restored into a
  disposable PostgreSQL database.

## Explicit Non-Goals

This design does not provide horizontal scaling, high availability, managed
database failover, guaranteed free capacity, enterprise authentication, a
service-level objective, or a disaster-safe backup destination. Those require
paid or separately managed infrastructure.

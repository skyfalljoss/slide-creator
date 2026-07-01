.PHONY: dev backend backend-dev frontend onlyoffice-dev onlyoffice-dev-down stack-up stack-down stack-logs migrate backup onlyoffice-shutdown

DEV_ONLYOFFICE_JWT_SECRET ?= slideforge-local-onlyoffice-dev-secret-2026

dev: onlyoffice-dev
	$(MAKE) -j2 backend-dev frontend DEV_ONLYOFFICE_JWT_SECRET="$(DEV_ONLYOFFICE_JWT_SECRET)"

backend:
	cd backend && uv run uvicorn app.main:app --reload --reload-dir app

backend-dev:
	cd backend && ONLYOFFICE_ENABLED=true ONLYOFFICE_PUBLIC_URL=http://localhost:8080 ONLYOFFICE_INTERNAL_URL=http://localhost:8080 ONLYOFFICE_API_URL=http://host.docker.internal:8000 ONLYOFFICE_JWT_SECRET="$(DEV_ONLYOFFICE_JWT_SECRET)" uv run uvicorn app.main:app --reload --reload-dir app

frontend:
	cd frontend && pnpm dev

onlyoffice-dev:
	DEV_ONLYOFFICE_JWT_SECRET="$(DEV_ONLYOFFICE_JWT_SECRET)" docker compose -f compose.dev.yaml up -d --wait onlyoffice

onlyoffice-dev-down:
	@if DEV_ONLYOFFICE_JWT_SECRET="$(DEV_ONLYOFFICE_JWT_SECRET)" docker compose -f compose.dev.yaml ps --status running --services | grep -qx onlyoffice; then \
		DEV_ONLYOFFICE_JWT_SECRET="$(DEV_ONLYOFFICE_JWT_SECRET)" docker compose -f compose.dev.yaml exec -T onlyoffice documentserver-prepare4shutdown.sh; \
	fi
	DEV_ONLYOFFICE_JWT_SECRET="$(DEV_ONLYOFFICE_JWT_SECRET)" docker compose -f compose.dev.yaml down

stack-up:
	docker compose --env-file .env up --build -d

stack-down:
	$(MAKE) onlyoffice-shutdown
	docker compose --env-file .env down

stack-logs:
	docker compose --env-file .env logs -f backend onlyoffice web

migrate:
	docker compose --env-file .env run --rm backend uv run alembic upgrade head

backup:
	@set -a; . ./.env; set +a; ./deploy/backup-postgres.sh

onlyoffice-shutdown:
	./deploy/shutdown-onlyoffice.sh

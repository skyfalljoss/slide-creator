.PHONY: dev backend frontend stack-up stack-down stack-logs migrate backup onlyoffice-shutdown

dev:
	$(MAKE) -j2 backend frontend

backend:
	cd backend && uv run uvicorn app.main:app --reload --reload-dir app

frontend:
	cd frontend && pnpm dev

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

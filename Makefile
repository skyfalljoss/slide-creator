.PHONY: dev backend frontend stack-up stack-down stack-logs migrate backup

dev:
	$(MAKE) -j2 backend frontend

backend:
	cd backend && uv run uvicorn app.main:app --reload --reload-dir app

frontend:
	cd frontend && pnpm dev

stack-up:
	docker compose up --build -d

stack-down:
	docker compose down

stack-logs:
	docker compose logs -f backend onlyoffice web

migrate:
	cd backend && uv run alembic upgrade head

backup:
	./deploy/backup-postgres.sh

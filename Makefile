.PHONY: dev backend frontend

dev:
	$(MAKE) -j2 backend frontend

backend:
	cd backend && uv run uvicorn app.main:app --reload --reload-dir app

frontend:
	cd frontend && pnpm dev

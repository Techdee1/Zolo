.PHONY: help db api web test test-backend test-frontend e2e check

help:
	@echo "make db | api | web | test | e2e | check"

db:            ## start Postgres
	cd backend && docker compose up -d postgres

api:           ## run the API on :8000 (needs backend/.env)
	cd backend && uv run alembic upgrade head && uv run python -m zolo.seed --if-empty && uv run uvicorn zolo.api.main:create_app --factory --port 8000

web:           ## run the web app on :3000
	cd frontend && pnpm dev

test-backend:
	cd backend && uv run pytest -q

test-frontend:
	cd frontend && pnpm check

test: test-backend test-frontend

e2e:
	cd frontend && pnpm build:e2e && pnpm e2e

check:         ## what CI checks, without the browser tests
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd frontend && pnpm check

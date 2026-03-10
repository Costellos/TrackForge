.PHONY: dev down logs migrate migrate-create shell-api shell-db test lint typecheck build help

# ─── Development ──────────────────────────────────────────

dev:
	docker compose -f docker-compose.dev.yml up --build

dev-bg:
	docker compose -f docker-compose.dev.yml up --build -d

down:
	docker compose -f docker-compose.dev.yml down

down-prod:
	docker compose down

logs:
	docker compose -f docker-compose.dev.yml logs -f

logs-api:
	docker compose -f docker-compose.dev.yml logs -f api

logs-worker:
	docker compose -f docker-compose.dev.yml logs -f worker

# ─── Database ─────────────────────────────────────────────

migrate:
	docker compose -f docker-compose.dev.yml exec api alembic upgrade head

migrate-create:
	@read -p "Migration name: " name; \
	docker compose -f docker-compose.dev.yml exec api alembic revision --autogenerate -m "$$name"

migrate-down:
	docker compose -f docker-compose.dev.yml exec api alembic downgrade -1

migrate-history:
	docker compose -f docker-compose.dev.yml exec api alembic history

# ─── Shells ───────────────────────────────────────────────

shell-api:
	docker compose -f docker-compose.dev.yml exec api bash

shell-db:
	docker compose -f docker-compose.dev.yml exec db psql -U trackforge -d trackforge

# ─── Testing & Quality ────────────────────────────────────

test:
	docker compose -f docker-compose.dev.yml exec api pytest

test-cov:
	docker compose -f docker-compose.dev.yml exec api pytest --cov=trackforge --cov-report=term-missing

lint:
	docker compose -f docker-compose.dev.yml exec api ruff check trackforge
	cd frontend && npm run lint

typecheck:
	docker compose -f docker-compose.dev.yml exec api mypy trackforge
	cd frontend && npm run typecheck

# ─── Production ───────────────────────────────────────────

build:
	docker compose build

prod-up:
	docker compose up -d

prod-migrate:
	docker compose exec api alembic upgrade head

# ─── Setup ────────────────────────────────────────────────

setup:
	cp -n .env.example .env || true
	@echo "Edit .env with your configuration, then run: make dev"

help:
	@echo "TrackForge — available commands:"
	@echo ""
	@echo "  make dev            Start dev environment (hot reload)"
	@echo "  make down           Stop dev environment"
	@echo "  make logs           Tail all logs"
	@echo "  make migrate        Run pending migrations"
	@echo "  make migrate-create Create a new migration"
	@echo "  make shell-api      Shell into API container"
	@echo "  make shell-db       Open psql in DB container"
	@echo "  make test           Run test suite"
	@echo "  make lint           Run linters"
	@echo "  make typecheck      Run type checkers"
	@echo "  make build          Build production images"
	@echo "  make setup          First-time setup (copy .env.example)"

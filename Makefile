# One place for every local command (FND-024, FND-026, FND-028). `make check` = all automated checks.
UV ?= uv
COMPOSE = docker compose --env-file .env -f infra/docker-compose.yml
LOAD_ENV = set -a && . ./.env && set +a

.PHONY: install deps-up deps-down up down migrate backend frontend \
        check check-repo check-backend check-frontend e2e

install:
	cd backend && $(UV) sync --frozen
	cd frontend && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm ci --no-audit --no-fund

deps-up:            ## database, Redis and local storage only
	$(COMPOSE) up -d --wait db redis storage

deps-down:
	$(COMPOSE) stop db redis storage

up:                 ## whole stack in containers (web on http://127.0.0.1:8080)
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

migrate:
	$(LOAD_ENV) && cd backend && $(UV) run alembic upgrade head

backend:
	$(LOAD_ENV) && cd backend && $(UV) run uvicorn app.main:create_app --factory --reload --port 8000

frontend:
	cd frontend && npm run dev

check: check-repo check-backend check-frontend

check-repo:
	python3 tools/check_repo.py

check-backend:
	cd backend && $(UV) lock --check
	cd backend && $(UV) run ruff format --check app tests
	cd backend && $(UV) run ruff check app tests
	cd backend && $(UV) run mypy app tests
	cd backend && $(UV) run pytest

check-frontend:
	cd frontend && npm run format:check
	cd frontend && npm run lint
	cd frontend && npm run typecheck
	cd frontend && npm test
	cd frontend && npm run build

e2e:
	cd frontend && npx playwright test

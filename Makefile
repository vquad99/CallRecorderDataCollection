# One place for every local command (FND-024, FND-026, FND-028). `make check` = all automated checks.
UV ?= uv
COMPOSE = docker compose --env-file .env -f infra/docker-compose.yml
LOAD_ENV = set -a && . ./.env && set +a

.PHONY: install deps-up deps-down up down migrate seed-dev key backend worker frontend \
        check check-repo check-backend check-frontend e2e journeys

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

seed-dev:           ## demo account per role + DEMO project (development only, uses DEMO_PASSWORD)
	$(LOAD_ENV) && cd backend && $(UV) run python -m app.cli seed-dev

key:                ## print a new DATA_ENCRYPTION_KEY
	@python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"

backend:
	$(LOAD_ENV) && cd backend && $(UV) run uvicorn app.main:create_app --factory --reload --port 8000

worker:             ## recording processing (needs REDIS_URL; without Redis the backend processes in-process)
	$(LOAD_ENV) && cd backend && $(UV) run celery -A app.worker worker --loglevel=INFO

frontend:
	cd frontend && npm run dev

check: check-repo check-backend check-frontend

check-repo:
	python3 tools/check_repo.py

check-backend:
	cd backend && $(UV) lock --check
	cd backend && $(UV) run ruff format --check app tests loadtest
	cd backend && $(UV) run ruff check app tests loadtest
	cd backend && $(UV) run mypy app tests loadtest
	cd backend && $(UV) run pytest

check-frontend:
	cd frontend && npm run format:check
	cd frontend && npm run lint
	cd frontend && npm run typecheck
	cd frontend && npm test
	cd frontend && npm run build

e2e:
	cd frontend && npx playwright test

# User journeys against the real backend (Option D). Needs the backend running on :8000 with
# EMAIL_FILE_DIR=$(E2E_OUTBOX) and `seed-dev` done; E2E_ADMIN_PASSWORD = DEMO_PASSWORD.
journeys:
	cd frontend && npx playwright test --config playwright.journeys.config.ts

# Conversation Collection Platform

Web application for collecting two-person conversation recordings with participant consent, an
automatic audio quality check and human QC.

Status: **Phase 1 live** at **https://dubdesk.live**: face-to-face recording in the browser,
participants and consent by email, tasks, automatic audio check, QC decisions, downloads with the
consent record and a details file, project exports (audio, metadata, both, progress report),
dashboards per role, audit log. Phone-call recording (Phase 2), transcription and app install are
not built yet. See `docs/BUILD_STATUS.md`
for the module-by-module state.

## Documents

| Read this | For |
|---|---|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | How each role uses the app, in plain language |
| [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md) | Step-by-step test with expected results (for the client) |
| [docs/HANDOVER.md](docs/HANDOVER.md) | Hosting, domain, email, storage, secrets, accounts, costs, open items, handover steps |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Environments and Render details |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decisions and open questions |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | Every requirement |

## Layout

```
backend/    FastAPI application, Alembic migrations, pytest tests
frontend/   React + TypeScript (Vite), Vitest and Playwright tests
infra/      Docker Compose for local services
tools/      repository checks used by CI
docs/       requirements, architecture, decisions, test plan, evidence
```

## Prerequisites

Python 3.12, [uv](https://docs.astral.sh/uv/) 0.13.1, Node.js 22, Docker with Compose v2, make.

## First-time setup

```bash
cp .env.example .env          # then replace every change-me value
make install                  # backend (uv, frozen lockfile) + frontend (npm ci)
make deps-up                  # PostgreSQL, Redis, local S3 storage in Docker
make migrate                  # apply database migrations
make seed-dev                 # optional: one demo account per role (password = DEMO_PASSWORD)
```

`make key` prints a value for `DATA_ENCRYPTION_KEY`. Development email (invitations, password
resets) is written as files to `EMAIL_FILE_DIR` instead of being sent.

## Run

```bash
make backend                  # API on http://127.0.0.1:8000  (health: /health/ready)
make frontend                 # UI on http://localhost:5173 (proxies /api and /health to the API)
```

Or the whole stack in containers: `make up` (UI on http://127.0.0.1:8080), `make down` to stop.

## Checks

```bash
make check                    # repo rules + backend (format, lint, types, tests) + frontend (format, lint, types, tests, build)
make e2e                      # browser test (PW_CHANNEL=chrome uses an installed Chrome)
make journeys                 # user journeys against a running backend (frontend/journeys/README.md)
```

Backend database tests need `TEST_DATABASE_URL` pointing at a database whose name ends in `_test`
(`.env.example` has one; `make deps-up` creates it). Without it they are skipped locally and reported
as skipped; CI sets `REQUIRE_DB_TESTS=1`, which turns a missing test database into a failure.

## Secrets

Never commit `.env`, credential files or keys. `.env.example` holds names and safe example values only.

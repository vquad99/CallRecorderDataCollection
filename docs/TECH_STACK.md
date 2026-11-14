# Technology stack

Status: pinned in Phase 1 (2026-11-09). Releases were resolved only from versions published at least
two weeks earlier: `exclude-newer = 2026-10-26` in `backend/pyproject.toml`, `npm install --before=2026-10-26`
(DECISIONS.md D-023). `tools/check_repo.py` (TA-ARCH-01) fails CI when a version below differs from
the lockfile or image tag it names.

Security fixes are the exception: a package with a published vulnerability (found by `pip-audit`
or `npm audit` in CI) takes its fixed release at once, through `exclude-newer-package` in
`backend/pyproject.toml` (2026-11-14: dnspython 2.9.2, opentelemetry-api 1.45.2).

## Pinned versions

| Component | Package | Version | Source |
|---|---|---|---|
| Backend framework | fastapi | 0.162.0 | uv.lock |
| ASGI toolkit | starlette | 1.10.0 | uv.lock |
| ASGI server | uvicorn | 0.54.0 | uv.lock |
| Validation | pydantic | 2.14.1 | uv.lock |
| Settings | pydantic-settings | 2.16.1 | uv.lock |
| ORM | sqlalchemy | 2.1.6 | uv.lock |
| Migrations | alembic | 1.20.1 | uv.lock |
| PostgreSQL driver | psycopg | 3.3.6 | uv.lock |
| Redis client | redis | 8.1.0 | uv.lock |
| Password hashing | argon2-cffi | 25.1.0 | uv.lock |
| Field encryption | cryptography | 50.0.2 | uv.lock |
| Email validation | email-validator | 2.3.0 | uv.lock |
| S3 client | boto3 | 1.43.118 | uv.lock |
| Numerics | numpy | 2.5.4 | uv.lock |
| Resampler (libsoxr) | soxr | 1.1.0 | uv.lock |
| WAV reading (libsndfile) | soundfile | 0.14.0 | uv.lock |
| Background jobs | celery | 5.6.3 | uv.lock |
| Fake S3 for tests | moto | 5.2.4 | uv.lock |
| Backend tests | pytest | 9.1.1 | uv.lock |
| Test HTTP client | httpx2 | 2.16.0 | uv.lock |
| Python lint/format | ruff | 0.17.2 | uv.lock |
| Python types | mypy | 2.4.0 | uv.lock |
| UI library | react | 19.3.1 | package-lock.json |
| UI rendering | react-dom | 19.3.1 | package-lock.json |
| Routing | react-router | 8.5.0 | package-lock.json |
| Build tool | vite | 8.3.5 | package-lock.json |
| Language | typescript | 6.0.3 | package-lock.json |
| Unit tests | vitest | 5.0.5 | package-lock.json |
| Test DOM | jsdom | 30.1.3 | package-lock.json |
| Component tests | @testing-library/react | 16.3.3 | package-lock.json |
| Accessibility checks | axe-core | 4.14.0 | package-lock.json |
| JS lint | eslint | 9.39.5 | package-lock.json |
| TS lint rules | typescript-eslint | 8.72.0 | package-lock.json |
| Accessibility lint | eslint-plugin-jsx-a11y | 6.10.2 | package-lock.json |
| Formatter | prettier | 3.9.10 | package-lock.json |
| Browser tests | @playwright/test | 1.64.1 | package-lock.json |
| Database image | postgres | 16.15-alpine | infra/docker-compose.yml |
| Redis image | redis | 7.4.12-alpine | infra/docker-compose.yml |
| Local S3 storage image | chrislusf/seaweedfs | 4.51 | infra/docker-compose.yml |
| Backend base image | python | 3.12.16-slim-bookworm | backend/Dockerfile |
| Frontend build image | node | 22.23.4-alpine | frontend/Dockerfile |
| Web server image | nginx | 1.28.3-alpine | frontend/Dockerfile |

Tooling outside the lockfiles: uv 0.13.1 (backend/Dockerfile, CI), Node.js 22.23.x (CI 22.23.4),
Python 3.12. GitHub Actions: actions/checkout@v7, actions/setup-node@v7, astral-sh/setup-uv@v10.3.3,
gitleaks/gitleaks-action@v3.

## Chosen, not yet pinned (later phases)

| Layer | Choice | Phase |
|---|---|---|
| Audio decoding of provider formats | FFmpeg from system packages (D-040) | 6 |
| ASR | Deepgram API through the ASR adapter, optional per project (D-018) | 7 |
| Error tracking, metrics | to choose | 10 |

## Known version issue

ESLint 9.39.5 is marked "no longer supported" by ESLint. It is used because eslint-plugin-jsx-a11y
6.10.2 (accessibility lint) does not accept ESLint 10 (npm peer-dependency conflict seen 2026-11-09).
Revisit when the plugin supports ESLint 10 (D-022).

## Build machine as found (2026-11-09, aws-dev)

Ubuntu 24.04.4, 4 CPU, 15 GiB RAM; Python 3.12.3; Node.js 22.23.3 / npm 10.9.9; Google Chrome
155.0.8059.84; Docker, FFmpeg and Redis not installed; root disk about 2 GB free after Phase 1 installs.
A PostgreSQL 16 server on the machine belongs to another project and is not used; Phase 1 tests ran
against a private throwaway PostgreSQL instance on port 55432.

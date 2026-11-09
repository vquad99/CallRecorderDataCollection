# Technology stack

Status: baseline chosen (runbook B4, spec 7); versions NOT pinned yet. Phase 1 picks current stable
releases, pins them in lockfiles (`backend/uv.lock` or equivalent, `frontend/package-lock.json`) and
fills the Version column from those lockfiles. No version is claimed before that (ARCH-003).

## Application stack

| Layer | Choice | Version | Pinned in |
|---|---|---|---|
| Frontend framework | React + TypeScript (strict) | to pin in Phase 1 | frontend/package-lock.json |
| Frontend build | Vite | to pin in Phase 1 | frontend/package-lock.json |
| Accessible components | to choose in Phase 1 (DECISIONS.md) | - | - |
| Backend framework | FastAPI | to pin in Phase 1 | backend lockfile |
| Validation | pydantic | to pin in Phase 1 | backend lockfile |
| ORM / migrations | SQLAlchemy + Alembic | to pin in Phase 1 | backend lockfile |
| Database | PostgreSQL | to pin in Phase 1 (container image tag) | infra/docker-compose |
| Queue | Celery + Redis | to pin in Phase 1 | backend lockfile, compose |
| Object storage | S3-compatible; MinIO locally | to pin in Phase 1 | compose |
| Audio | FFmpeg + numpy/soundfile | to pin in Phase 1 | Dockerfile, backend lockfile |
| Reverse proxy | Nginx or managed ingress | to pin in Phase 1 | infra |
| Password hashing | Argon2id library | to pin in Phase 2 | backend lockfile |
| PWA | web manifest + service worker | to pin in Phase 10 | frontend lockfile |
| ASR (optional per project) | Deepgram API through the ASR adapter (D-018) | API/model version recorded per job; capabilities NOT VERIFIED until Phase 7 | backend lockfile (client library, if used) |

## Test and quality tools

| Purpose | Choice | Version |
|---|---|---|
| Backend tests | pytest | to pin in Phase 1 |
| Frontend unit tests | Vitest + React Testing Library | to pin in Phase 1 |
| End-to-end | Playwright | to pin in Phase 1 |
| Python lint/format/types | to choose in Phase 1 (e.g. ruff + mypy) | to pin |
| TS lint/format | to choose in Phase 1 (e.g. ESLint + Prettier) | to pin |
| Secret scan | to choose in Phase 1 | to pin |
| Dependency scan | to choose in Phase 1 | to pin |

## Build machine as found (2026-11-09, aws-dev)

These are the tools present on the machine, not project pins.

| Tool | Found |
|---|---|
| OS | Ubuntu 24.04.4 LTS, 4 CPU, 15 GiB RAM |
| Python | 3.12.3 (/usr/bin/python3) |
| Node.js / npm | v22.23.3 / 10.9.9 |
| psql client | 16.15 (the running PostgreSQL server belongs to another project and is not used) |
| Google Chrome | 155.0.8059.84 |
| Docker | MISSING |
| FFmpeg / ffprobe | MISSING |
| Redis | MISSING |
| Free disk | 3.5 GB of 58 GB (94 % used) |

Phase 1 cannot run its Docker-based setup here until Docker and FFmpeg are installed and disk is freed
(DECISIONS.md B-08).

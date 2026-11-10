# Deployment

Status: planned (Phase 0). Nothing is deployed. Requirement IDs: OPS-*, FND-024..029, SEC-002..003,
SEC-008, SEC-014. Cloud provider, account and region are open (DECISIONS.md B-04).

## 1. Environments (OPS-001)

| Environment | Where | Purpose |
|---|---|---|
| local | developer machine, Docker Compose | development, automated tests |
| test/staging | cloud, same shape as production | provider proof, load tests, PWA install tests, restore tests |
| production | cloud, region chosen for data residency | live use |

## 2. Components (OPS-002)

| Component | local | staging / production |
|---|---|---|
| Frontend (static build) | Vite dev server / Nginx | Nginx or CDN behind TLS |
| Backend (FastAPI) | container | containers, 2+ replicas |
| Workers (Celery: recording processing now; webhooks, QC, exports later) | `worker` container | containers, scaled per queue (D-043) |
| ASR worker | same worker image, `asr` queue | same; calls the Deepgram API (key in secret manager); idle when AI transcription is off (D-018) |
| PostgreSQL | container with volume | managed PostgreSQL, automated encrypted backups |
| Redis | container | managed Redis |
| Object storage | SeaweedFS container (S3 API, D-020) | Wasabi private bucket (D-019): encryption, versioning, lifecycle as confirmed in Wasabi docs |
| Reverse proxy / ingress | Nginx container | Nginx or managed ingress, TLS |
| Monitoring and logs | container logs | central logs, metrics, error tracking, alerts |
| Secrets | `.env` (never committed) | cloud secret manager (OPS-003) |

## 3. Local setup (Phase 1, FND-024..029)

See README.md. Commands (Makefile): `make install`, `make deps-up` (PostgreSQL, Redis, SeaweedFS in
Docker, bound to 127.0.0.1), `make migrate`, `make backend`, `make frontend`, `make check`, `make e2e`,
`make up` / `make down` (whole stack in containers, web on 127.0.0.1:8080). The dev-only demo-account
seed arrives with the users table in Phase 2 (D-025). CI runs the same checks plus a container job that
starts every service, migrates, and proves data survives a database restart (D-026).

## 4. Release procedure (Phase 10)

1. CI green on the release commit (lint, types, tests, secret and dependency scans).
2. Build and tag images.
3. Run database migrations as a separate, controlled step (OPS-007).
4. Deploy backend and workers; wait for `/health/ready`.
5. Deploy frontend; service worker update prompt reaches users (PWA-005).
6. Smoke test; watch alerts.

## 5. Operations (to be completed in Phase 10)

Commands (run where the backend's settings are available):

| Command | When | What it does |
|---|---|---|
| `python -m app.cli retention` | daily (scheduler) | Deletes stored files older than each project's retention rules, with audit entries |
| `python -m app.cli recover-recordings` | on demand | Sends every recording left half-done by a stopped process to processing again; the web processes also do this at start-up and every `RECOVERY_INTERVAL_SECONDS` (D-055) |

| `python -m app.cli verify-assets [--deep N]` | weekly | Checks every stored file's presence, size and checksum label; with `--deep N` downloads N at random and hashes them again; exit code 1 when anything is wrong (D-056) |
| `python -m app.cli storage-orphans [--delete]` | monthly | Lists (or deletes) stored files no record points to, older than 24 h; backups are never touched (D-056) |
| `infra/backup/backup.sh` (`KEEP_DAYS=N` to prune) | daily | Database dump into the private storage under `backups/db/` with its SHA-256 (D-058) |
| `infra/backup/restore.sh <key>` | when needed | Checks the backup, stops backend and worker, restores, starts them again (D-058) |

Scaling (D-059): `WEB_CONCURRENCY` (web processes), `WORKER_CONCURRENCY` (processing slots per
worker container), `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` (connections per web process). Monitoring
(D-057): `SLOW_REQUEST_MS` (1000) and `SLOW_QUERY_MS` (250) turn slow answers into warnings; every
request log line carries `db_queries` and `db_ms`; `/health/ready` checks database, Redis and
storage. Web server: `MEDIA_ORIGINS` names where recordings play from (Wasabi by default, D-061).

Recovery settings: `PROCESSING_PICKUP_SECONDS` (60), `PROCESSING_STALE_MINUTES` (15),
`RECOVERY_INTERVAL_SECONDS` (60; 0 = start-up only).

| Item | Requirement | Status |
|---|---|---|
| Infrastructure configuration in repository | OPS-002 | NOT STARTED |
| Database backups + restore test | OPS-004, SEC-008 | NOT STARTED |
| Object storage lifecycle | OPS-004 | NOT STARTED |
| Health checks, TLS, domain, DNS | OPS-005 | NOT STARTED (domain: B-09) |
| Alerting and log retention | OPS-006 | NOT STARTED |
| Rollback procedure | OPS-008 | NOT STARTED |
| Disaster recovery runbook | OPS-008 | NOT STARTED |
| Incident runbook | OPS-008 | NOT STARTED |
| Clean deployment reproduced from this document | OPS-009 | NOT STARTED |

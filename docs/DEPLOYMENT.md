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
| Workers (Celery: webhooks, media, qc, exports) | container | containers, scaled per queue |
| ASR workers | optional (CPU, small models) | GPU instances (B-07) |
| PostgreSQL | container with volume | managed PostgreSQL, automated encrypted backups |
| Redis | container | managed Redis |
| Object storage | MinIO container | private S3-compatible bucket, encryption, versioning, lifecycle |
| Reverse proxy / ingress | Nginx container | Nginx or managed ingress, TLS |
| Monitoring and logs | container logs | central logs, metrics, error tracking, alerts |
| Secrets | `.env` (never committed) | cloud secret manager (OPS-003) |

## 3. Local setup (Phase 1, FND-024..029)

To be written in Phase 1 as exact commands, e.g. one command to start dependencies, one to migrate,
one dev-only seed, one test command. Requires Docker, FFmpeg and disk space on the build machine (B-08).

## 4. Release procedure (Phase 10)

1. CI green on the release commit (lint, types, tests, secret and dependency scans).
2. Build and tag images.
3. Run database migrations as a separate, controlled step (OPS-007).
4. Deploy backend and workers; wait for `/health/ready`.
5. Deploy frontend; service worker update prompt reaches users (PWA-005).
6. Smoke test; watch alerts.

## 5. Operations (to be completed in Phase 10)

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

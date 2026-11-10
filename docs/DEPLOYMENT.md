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

### Proxy addresses, report time zone, health checks (D-064, D-065)

- `FORWARDED_ALLOW_IPS`: the address (or subnet) of the proxy in front of the backend - in the local
  stack the web container's fixed address `172.30.57.10`. With a cloud load balancer in front of
  nginx, configure nginx's real-IP module for the balancer and keep this pointing at nginx. Never
  `*`: anyone could choose the address they are counted under (login limits, rate limits, audit).
- `REPORT_TIMEZONE` (default `Asia/Kolkata`): calendar days for dashboards.
- nginx answers `/health/live` to anyone and `/health/ready` only to private networks (load
  balancer, monitoring, the host). Its access log leaves out query strings, so one-time sign-in
  tokens never reach the log.

### Hosted check copy on Render (D-077)

`render.yaml` at the repository root describes a staging copy on Render, Singapore region:
`ccp-web` (public; nginx serving the app and forwarding /api to the API), `ccp-api` (private
service; only reachable over Render's private network), `ccp-db` (PostgreSQL 16, private network
only). No Redis or worker: on staging the API processes recordings itself. Before each deploy goes
live, a pre-deploy step (`python -m app.cli prepare-deploy`) runs the migrations, creates the
first Super Admin and, only when `ALLOW_DEMO_SEED` is `true`, the demo accounts. It is one command
with no quotes or `&&`: Render ran a quoted `sh -c "..."` as a single word on the first deploy.

Steps in the Render dashboard (owner's account):

1. Give Render access to the GitHub repository (Account Settings > Git Deployment Credentials, and
   the Render GitHub app's repository access for `vquad99/CallRecorderDataCollection`).
2. New > Blueprint > choose the repository, branch `main`, path `render.yaml`.
3. Enter the values Render asks for:
   - `DATA_ENCRYPTION_KEY`: the line in `~/.config/ccp/render_data_encryption_key` on the
     development server (keep a copy: without it stored phone numbers and emails cannot be read).
   - `STORAGE_ACCESS_KEY_ID`, `STORAGE_SECRET_ACCESS_KEY`: Wasabi keys (files go under `staging/`).
   - `ADMIN_EMAIL`, `ADMIN_PASSWORD` (12+ characters): the first Super Admin.
   - `PUBLIC_APP_URL`: `https://ccp-web.onrender.com` (if Render shows a different address for
     ccp-web after creation, change this value to it, without a trailing slash).
   - `DEMO_PASSWORD`: 16+ characters if demo accounts are wanted (then set `ALLOW_DEMO_SEED` to
     `true` on ccp-api and redeploy); otherwise leave any value.
4. Deploy Blueprint. Cost at Render's published prices (2026-11-11): two `starter` services at
   USD 7 each, Postgres `basic-256mb` USD 6 plus storage (USD 0.30 per GB).

Known limits of the check copy:

- Emails (invitations, password resets, consent links) are written inside the container and not
  sent until a mail service is configured (B-13). Personal links can be copied from the
  Participants page instead.
- How Render passes the visitor's address is not documented by Render. Tested on the live copy
  (2026-11-10): the address reached the API correctly, but a false `X-Forwarded-For` sent by the
  visitor dodged the per-address sign-in limit (the per-account limit held). Fixed: on Render,
  nginx takes the address from `CF-Connecting-IP` (`REAL_IP_FROM` / `REAL_IP_HEADER`) and sends the
  API exactly one address. Re-tested after the change on 2026-11-10 at 19:19 IST: 22 sign-in
  attempts with a different false address in `X-Forwarded-For`, `X-Real-IP` and `True-Client-IP`
  each time gave 401 twenty times, then 429. A request that sets `CF-Connecting-IP` itself is
  refused by Cloudflare before it reaches Render (403, error 1000).
- Free plans are not used: a free Postgres is deleted after 30 days and private services and
  workers have no free plan.

### Production on Render, Stage 1 (D-080)

`render.production.yaml` describes production: its own services and its own empty database, so the
check copy above stays as it is. `ccp-prod-web` (public), `ccp-prod-api` (private),
`ccp-prod-worker` (background worker: turns uploads into delivery files and runs the automatic
audio check), `ccp-prod-redis` (private Key Value: the work queue and shared sign-in limits; never
evicts a queued job), `ccp-prod-db` (PostgreSQL 16, private, point-in-time recovery). The worker
copies its settings from the API, so the two cannot disagree. Files go under `production/` in the
Wasabi bucket. `APP_ENV=production` makes the application refuse to start without real email
(SMTP), Redis, an https address and storage keys; there are no demo accounts.

Before creating it, the owner needs: an SMTP mail account (B-13; host, user name, password and a
sender address on a domain the mail service has verified), and approval of the cost below.

Steps in the Render dashboard:

1. New > Blueprint > the same repository, branch `main`, Blueprint path `render.production.yaml`.
2. Enter the values Render asks for: `DATA_ENCRYPTION_KEY` (a NEW key, made with
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`,
   kept in the password manager), Wasabi keys, `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
   `EMAIL_FROM` (for example `Conversation Collection <no-reply@yourdomain>`), `ADMIN_EMAIL`,
   `ADMIN_PASSWORD` (12+ characters), and `PUBLIC_APP_URL` = the address Render shows for
   `ccp-prod-web` (or the custom domain), without a trailing slash.
3. Deploy. If `PUBLIC_APP_URL` was guessed and Render shows another address, correct it on
   `ccp-prod-api` and redeploy (the worker copies it).
4. Sign in as the Super Admin, turn on two-step sign-in for that account, then create the team.

Cost at Render's published prices (read 2026-11-11): three `starter` services at USD 7 each, Key
Value `starter` (256 MB) USD 10, Postgres `basic-256mb` USD 6 plus storage (USD 0.30 per GB):
about USD 37 a month, plus Wasabi storage. The check copy costs about USD 20 a month on top while
it is kept.

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

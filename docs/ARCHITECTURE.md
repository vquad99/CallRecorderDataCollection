# Architecture

Status: proposed (Phase 0). Nothing is built. Items marked **NOT VERIFIED** depend on a telephony
provider that has not been selected (DECISIONS.md B-01). Related: DATABASE.md, API_CONTRACT.md,
SECURITY.md, AUDIO_SPECIFICATION.md, DEPLOYMENT.md, TECH_STACK.md.

## 1. Shape (ARCH-001)

A modular monolith: one backend application, one worker image, one web frontend, plus managed services.

```
             Browser / installed PWA (React + TypeScript)
               |  HTTPS, session cookie + CSRF token
               v
         Nginx or managed ingress (TLS, static files, size limits)
               |
               v
  FastAPI application  /api/v1  ---------------------------------+
  | auth | users | projects | participants | tasks | telephony    |
  | recording | storage | audio_qc | asr | transcription           |
  | transcript_qc | exports | dashboard | audit | settings         |
  +------+-------------------+------------------+-----------------+
         |                   |                  |
     PostgreSQL            Redis           Private S3-compatible storage
   (all state, no audio)  (queue, limits)  (audio, transcripts, exports)
         ^                   |
         |                   v
  Celery workers: webhooks | media | qc | asr | exports
         |
         +--> Telephony provider API  (only through the telephony adapter)
         +--> Deepgram API             (only through the ASR adapter; optional per project)

  Telephony provider --signed webhooks--> /api/v1/webhooks/telephony/<provider>
```

## 2. Repository layout (created in Phase 1, runbook D1/D2)

```
backend/
  app/main.py                 application factory
  app/core/                   config.py, logging.py, security.py, errors.py, permissions.py
  app/api/router.py           mounts module routers under /api/v1
  app/db/                     base.py, session.py, migrations/ (Alembic)
  app/modules/<module>/       models, schemas, service, router per module
  app/adapters/               telephony/, asr/, storage/  - the only place provider code lives
  app/tests/
  pyproject.toml, Dockerfile
frontend/
  src/{app,api,auth,components,features,layouts,routes,styles,test}
  public/  (manifest.webmanifest, icons)
  package.json, vite.config.ts, tsconfig.json
infra/                        docker-compose (local), nginx, deployment configuration
docs/
```

## 3. Stack

See TECH_STACK.md. Baseline (runbook B4): React + TypeScript, FastAPI, PostgreSQL + Alembic,
Celery + Redis, FFmpeg + a tested Python audio library, private S3-compatible storage (Wasabi in cloud,
MinIO locally, D-019),
Docker, Nginx or managed ingress, web manifest + service worker; pytest, Vitest + React Testing Library,
Playwright.

## 4. Cross-cutting rules

- Every route sits under `/api/v1` and declares a permission from one central registry (ROLE-009/010).
- Every query is scoped to the caller's projects and assignments in the service layer; a changed ID in a
  URL returns 403/404, never another project's data.
- Workflow state (task, call, job, QC) lives in PostgreSQL; transitions go through one service per state
  machine, in a transaction with their history row (TASK-009/010).
- External services not configured return a truthful `Not configured` state (GEN-004).
- No audio bytes in PostgreSQL; only storage keys and metadata (DB-006).
- Security model: SECURITY.md.

## 5. Permission matrix (ROLE-008)

Legend: **F** full, **O** own (member) projects only, **A** items assigned to the user only,
**S** read-only on explicitly shared project results, **R** read, **-** none.
TA-ROLE-01 is generated from this table.

| Capability (permission code) | Super Admin | Project Admin | Moderator | Transcriber | QC Executive | Client Viewer |
|---|---|---|---|---|---|---|
| System settings, integrations, provider accounts (`settings.manage`) | F | - | - | - | - | - |
| Create/disable users, assign roles (`users.manage`) | F | - | - | - | - | - |
| Project membership (`projects.members`) | F | O | - | - | - | - |
| Create projects (`projects.create`) | F | - | - | - | - | - |
| Edit project settings (`projects.manage`) | F | O | - | - | - | - |
| Participant IDs, language, dialect (`participants.view`) | F | O | A | A (IDs) | A (IDs) | S (IDs) |
| Participant phone number (`participants.contact`) | F | O | A, if project policy allows | - | - | - |
| Participant contact export (`participants.export`) | F | O, explicit grant | - | - | - | - |
| Consent records (`consent.capture`, `consent.view`) | F | O (R) | A | - | - | - |
| Create / assign / reassign tasks (`tasks.assign`) | F | O | - | - | - | - |
| See tasks (`tasks.view`) | F | O | A | A | A | - |
| Start / control calls (`calls.start`) | - | - | A | - | - | - |
| End participant conference (`calls.end`) | F | O | A | - | - | - |
| Face-to-face recording (`recordings.create`) | - | - | A | - | - | - |
| Play audio (`recordings.view`) | F | O | A | A | A | S (final assets) |
| Download audio (`recordings.download`) | F | O | - | - | - | S (final assets) |
| Audio QC decision (`audio_qc.review`) | F | O (R) | - | - | A | - |
| Edit transcripts (`transcripts.edit`) | F | O (R) | - | A | A (annotate if granted) | - |
| Transcript QC decision (`transcripts.review`) | F | O (R) | - | - | A | - |
| Reopen approved transcript (`transcripts.reopen`) | F | O (reason + audit) | - | - | - | - |
| Exports (`exports.create`) | F | O | - | - | - | S (no personal data) |
| Dashboards (`dashboard.view`) | F | O | own work | own work | own work | S |
| Audit log (`audit.view`) | F | O | - | - | - | - |
| Webhook event viewer (`webhooks.view`) | F | - | - | - | - | - |
| Delete assets (`assets.delete`) | F | O (request only) | - | - | - | - |
| Internal staff notes (`notes.view`) | F | O | A | A | A | - |

Proposed, not stated by the sources: only Super Admin creates users and projects (D-010).

## 6. Telephony (Module 6) - provider-dependent, NOT VERIFIED

Adapter interface (runbook I2; internal names, not provider endpoints):
`start_call_to_a`, `add_b_to_conference`, `join_moderator`, `set_mute`, `start_recording`,
`moderator_leave`, `end_conference`, `get_recording`, `verify_webhook`.
Each implementation is written only from the provider's official documentation, recorded in
docs/integrations/.

Call state machine (runbook I3), stored in `call_sessions` with every transition in `call_events`:

```
CREATED -> CALLING_A -> A_CONNECTED -> ADDING_B -> B_CONNECTED -> MODERATOR_CONNECTED
  -> CONSENT_PENDING -> CONSENT_CONFIRMED -> RECORDING -> MODERATOR_LEFT
  -> PARTICIPANTS_CONTINUING -> COMPLETED
any state -> FAILED | CANCELLED (with reason)
```

Rules: no participant recording before CONSENT_CONFIRMED; consent refusal ends/cancels per project
policy; moderator departure never ends the conference; only `calls.end` ends it; webhooks may repeat or
arrive late and are applied idempotently; invalid transitions fail safely.

Moderator path: proposed through the provider's browser (WebRTC) client, so 50 conferences need 100
phone legs; if the provider has none, the moderator needs a phone leg and the count is 150 (D-008).

Webhooks: verify signature -> store event with unique provider event ID -> acknowledge quickly ->
process on the `webhooks` queue -> retry transient failures -> dead-letter permanent failures -> visible
in the admin webhook viewer. Recording URLs from webhooks are fetched only from the provider's allowed
hosts through the authenticated API (TEL-035).

Channel separation, decided at Gate 5 from evidence:

| Option | How | Status |
|---|---|---|
| T1 Provider multi-track recording | one track per participant | NOT VERIFIED |
| T2 Per-leg recording | A's leg and B's leg recorded separately, aligned by provider timestamps | NOT VERIFIED |
| T3 Live media streams | each participant's audio streamed to our receiver, written as PCM | NOT VERIFIED |
| Rejected | provider mixed (mono) recording | cannot be separated; never copied to L/R |

Audio handling for telephony: AUDIO_SPECIFICATION.md section 2.

## 7. Face-to-face (Module 7)

Capture, chunked upload, recovery and conversion: AUDIO_SPECIFICATION.md section 3. In short:
AudioWorklet raw PCM (not MediaRecorder), browser processing requested off, ~5-second chunks uploaded
during recording (nothing kept in browser storage), server assembles the original, worker derives the
16 kHz mono s16 WAV, both validated and linked.

## 8. Storage layout (STOR-002)

```
<project>/face-to-face/YYYY/MM/DD/<task>/original/
<project>/face-to-face/YYYY/MM/DD/<task>/derived/
<project>/telephony/YYYY/MM/DD/<task>/provider-original/
<project>/telephony/YYYY/MM/DD/<task>/final/
<project>/transcripts/<task>/
<project>/metadata/
<project>/exports/<export>/        (temporary, expiring)
```

Task and export IDs are random UUIDs. Bucket (Wasabi in cloud, MinIO locally): public access blocked, server-side encryption,
versioning, lifecycle rules per project retention policy. Access only through short-lived signed URLs
issued after a permission check.

## 9. Background jobs

| Queue | Jobs |
|---|---|
| webhooks | apply verified provider events, idempotently |
| media | fetch provider recordings, assemble chunks, build stereo, convert, hash, validate |
| qc | audio QC (read-only on sources) |
| asr | transcription through the ASR adapter (Deepgram API); skipped when the project has AI transcription off |
| exports | build export packages with manifest and checksums; expire old bundles |

Every job stores status, attempts and last error; bounded retries; permanent failures visible to admins.

## 10. Environments

local (Docker Compose), test/staging (cloud), production (cloud). Details: DEPLOYMENT.md.
Capacity claims come only from staging/production load tests (CAP-004).

# API contract

Status: planned (Phase 0). No endpoint exists. Every route below is under `/api/v1` (FND-012) except
health checks. Each route declares one permission (ARCHITECTURE.md section 5); responses are scoped to
the caller's projects and assignments. Exact request/response schemas are written as OpenAPI from the
code in each phase; this file lists the planned surface so the traceability table can point at it.

## Conventions

- JSON bodies; UTF-8; ISO-8601 UTC timestamps.
- Error body: `{"error": {"code": "...", "message": "...", "request_id": "..."}}`; no stack traces.
- Validation errors 422; auth 401; permission 403; not found or not visible 404; conflict 409
  (state transition, stale version); rate limit 429 with `Retry-After`.
- State-changing requests need the CSRF header; session is an HttpOnly cookie.
- List endpoints: `page`, `page_size`, `sort`, filters as query parameters.
- External service not configured: 503 with code `NOT_CONFIGURED` (GEN-004).

## Health (FND-007)

| Method | Path | Notes |
|---|---|---|
| GET | /health/live | process alive |
| GET | /health/ready | database (and queue) reachable; clear failure otherwise |

## Auth (AUTH-*)

| Method | Path | Permission |
|---|---|---|
| POST | /auth/login | public, throttled |
| POST | /auth/logout | authenticated |
| GET | /auth/me | authenticated |
| POST | /auth/password/forgot | public, throttled; same response whether or not the email exists |
| POST | /auth/password/reset | public, single-use token |
| GET | /auth/sessions | authenticated (own) |
| DELETE | /auth/sessions/{id} | authenticated (own) or `users.manage` |
| POST | /auth/mfa/enroll, /auth/mfa/verify | authenticated |

## Users and roles (USER-*, ROLE-*)

| Method | Path | Permission |
|---|---|---|
| GET, POST | /users | `users.manage` |
| GET, PATCH | /users/{id} | `users.manage` |
| POST | /users/{id}/disable, /users/{id}/enable | `users.manage` |
| PUT | /users/{id}/roles | `users.manage` |
| POST | /users/import/preview, /users/import/confirm | `users.manage` |
| GET | /users/export | `users.manage` |
| GET | /roles, /permissions | `users.manage` |

## Settings (CAP-*)

| Method | Path | Permission |
|---|---|---|
| GET, PATCH | /settings | `settings.manage` |

## Projects (PROJ-*)

| Method | Path | Permission |
|---|---|---|
| GET | /projects | member |
| POST | /projects | `projects.create` |
| GET, PATCH | /projects/{id} | member / `projects.manage` |
| POST | /projects/{id}/status | `projects.manage` (reopen needs reason) |
| GET, PUT | /projects/{id}/languages, /audio-rules, /guidelines, /retention | member / `projects.manage` |
| GET, POST, DELETE | /projects/{id}/members | `projects.members` |

## Participants (PART-*)

| Method | Path | Permission |
|---|---|---|
| GET, POST | /projects/{id}/participants | `participants.view` / `participants.manage` |
| GET, PATCH | /participants/{id} | `participants.view` / `participants.manage` (corrections audited) |
| POST | /participants/{id}/delete-request | `participants.manage` |
| GET | /projects/{id}/participants/export | `participants.export` |
| GET, POST | /tasks/{id}/consent | `consent.view` / `consent.capture` |

## Tasks (TASK-*)

| Method | Path | Permission |
|---|---|---|
| GET, POST | /tasks | `tasks.view` / `tasks.assign` |
| GET | /tasks/{id} | `tasks.view` |
| POST | /tasks/{id}/transition | depends on target state; body `{to, reason_code, comment}` |
| POST | /tasks/{id}/assign | `tasks.assign` (reason required on reassignment) |
| GET, POST | /tasks/{id}/comments | `tasks.view` |
| GET | /tasks/{id}/history | `tasks.view` |

## Storage and face-to-face recording (STOR-*, FTF-*)

| Method | Path | Permission |
|---|---|---|
| POST | /tasks/{id}/recordings | `recordings.create` |
| PUT | /recordings/{id}/chunks/{seq} | `recordings.create` (sha256 header checked) |
| POST | /recordings/{id}/complete | `recordings.create` |
| POST | /recordings/{id}/interrupted | `recordings.create` |
| GET | /recordings/{id} | `recordings.view` |
| GET | /assets/{id} | `recordings.view` |
| POST | /assets/{id}/download-url | `recordings.download` (short-lived signed URL) |
| POST | /assets/{id}/delete-request | `assets.delete` |
| GET | /storage/usage | `dashboard.view` |

## Telephony (TEL-*) - BLOCKED until Gate 5

| Method | Path | Permission |
|---|---|---|
| POST | /tasks/{id}/calls | `calls.start` |
| GET | /calls/{id} | `calls.start` or `tasks.view` |
| POST | /calls/{id}/add-b | `calls.start` |
| POST | /calls/{id}/moderator/join, /moderator/leave | `calls.start` |
| POST | /calls/{id}/mute | `calls.start` |
| POST | /calls/{id}/consent | `consent.capture` |
| POST | /calls/{id}/end | `calls.end` |
| GET | /calls/{id}/events | `tasks.view` |
| POST | /webhooks/telephony/{provider} | provider signature only |
| GET | /admin/webhook-events | `webhooks.view` |
| POST | /admin/webhook-events/{id}/retry | `webhooks.view` |

## Audio QC (AQC-*)

| Method | Path | Permission |
|---|---|---|
| GET | /audio-qc/queue | `audio_qc.review` |
| GET | /audio-qc/{asset_id} | `audio_qc.review` |
| POST | /audio-qc/{asset_id}/decision | `audio_qc.review` |

## AI transcription (ASR-*)

| Method | Path | Permission |
|---|---|---|
| GET | /transcription-jobs | `asr.view` (admin) |
| POST | /transcription-jobs/{id}/retry, /cancel | `asr.manage` |

## Human transcription and transcript QC (TRN-*, TQC-*)

| Method | Path | Permission |
|---|---|---|
| GET | /transcription/queue | `transcripts.edit` |
| POST | /transcription/assignments | `tasks.assign` |
| GET | /transcripts/{task_id} | `transcripts.edit` / `transcripts.review` |
| PUT | /transcripts/{task_id}/draft | `transcripts.edit` (version check -> 409 on concurrent edit) |
| POST | /transcripts/{task_id}/autosave | `transcripts.edit` |
| POST | /transcripts/{task_id}/submit | `transcripts.edit` |
| GET | /transcripts/{task_id}/revisions | `transcripts.edit` / `transcripts.review` |
| POST | /transcript-qc/{task_id}/decision | `transcripts.review` |
| POST | /transcripts/{task_id}/reopen | `transcripts.reopen` (reason required) |

## Exports (EXP-*)

| Method | Path | Permission |
|---|---|---|
| POST | /exports | `exports.create` (filters validated; personal data needs explicit grant) |
| GET | /exports/{id} | `exports.create` |
| POST | /exports/{id}/download-url | `exports.create` (short-lived; audited) |

## Dashboards (DASH-*)

| Method | Path | Permission |
|---|---|---|
| GET | /dashboard/summary, /dashboard/productivity, /dashboard/qc, /dashboard/failures, /dashboard/storage, /dashboard/provider-usage | `dashboard.view`; filters: project, date range, language, dialect, mode, staff, status |

## Audit (SEC-*)

| Method | Path | Permission |
|---|---|---|
| GET | /audit-logs | `audit.view` |

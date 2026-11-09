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
- Request limits (D-052): bodies over MAX_REQUEST_BYTES (2.5 MB; audio chunks MAX_CHUNK_BYTES, 8 MB)
  get 413 `PAYLOAD_TOO_LARGE`; a NUL character in the path, query string or a JSON body gets 422
  `VALIDATION_ERROR`. Every /api response carries `Cache-Control: no-store` and
  `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`.
- An object in a project the caller cannot see answers exactly like an object that does not exist.

## Health (FND-007)

| Method | Path | Notes |
|---|---|---|
| GET | /health/live | process alive |
| GET | /health/ready | 200 `{"status":"ready","checks":{...}}` or 503 `{"status":"not_ready",...}`; checks: database, redis (`ok` / `error` / `not_configured`) |

## Meta (built in Phase 1)

| Method | Path | Notes |
|---|---|---|
| GET | /api/v1/version | public; `{name, version, environment}` |

## Auth (AUTH-*)

| Method | Path | Permission |
|---|---|---|
| GET | /auth/csrf | public; sets the CSRF cookie |
| POST | /auth/login | public, throttled |
| POST | /auth/logout | authenticated |
| GET | /auth/me | authenticated |
| POST | /auth/password/forgot | public, throttled; same response whether or not the email exists |
| POST | /auth/password/reset | public, single-use token |
| GET | /auth/sessions | authenticated (own) |
| DELETE | /auth/sessions/{id} | authenticated (own) or `users.manage` |
| POST | /auth/password/change | authenticated |
| POST | /auth/mfa/enroll, /auth/mfa/confirm, /auth/mfa/disable | authenticated |

## Users and roles (USER-*, ROLE-*)

| Method | Path | Permission |
|---|---|---|
| GET, POST | /users | `users.manage` |
| GET, PATCH | /users/{id} | `users.manage` |
| POST | /users/{id}/disable, /users/{id}/enable | `users.manage` |
| PUT | /users/{id}/roles | `users.manage` |
| POST | /users/import/preview, /users/import/confirm | `users.manage` |
| GET | /users/export | `users.manage` |
| POST | /users/{id}/send-password-link | `users.manage` |
| POST | /users/{id}/sessions/revoke | `users.manage` |
| GET | /roles | `users.manage` |

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
| GET, PUT | /projects/{id}/asr | member / `projects.manage` (AI transcription on/off, Deepgram settings; shows Not configured without a key) |
| GET, POST, DELETE | /projects/{id}/members | GET: `projects.view`; POST/DELETE: `projects.members` |
| GET | /projects/{id}/member-candidates | `projects.members` (D-032) |

## Participants (PART-*)

| Method | Path | Permission |
|---|---|---|
| GET, POST | /projects/{id}/participants | `participants.view` / `participants.manage` |
| POST | /projects/{id}/participants/link | `participants.manage` (add an existing participant by code) |
| GET, PATCH | /projects/{id}/participants/{pid} | `participants.view` / `participants.manage` (corrections audited) |
| POST | /projects/{id}/participants/{pid}/delete | `participants.manage` (reason required; removes personal data) |
| GET | /projects/{id}/participants/{pid}/consent | `consent.view` + participant manager, or the moderator on an open task with that person (D-049); each participant row carries `consent_visible` |
| GET | /projects/{id}/participants/export | `participants.export` |
| POST | /tasks/{id}/consent | `consent.capture` + the task's assigned moderator, whatever the role (D-051) |

## Tasks (TASK-*)

| Method | Path | Permission |
|---|---|---|
| GET, POST | /tasks | `tasks.view` / `tasks.assign` |
| GET | /tasks/{id} | `tasks.view` |
| POST | /tasks/{id}/transition | depends on target (backend/app/modules/tasks/workflow.py); body `{to, reason_code, comment}`; platform-only targets refused (D-037) |
| POST | /tasks/{id}/assign | `tasks.assign` (reason required on reassignment) |
| POST | /tasks/{id}/comments | `tasks.view` |
| GET | /tasks/{id}/timeline | `tasks.view` (status history, assignments, comments) |

## Storage and face-to-face recording (STOR-*, FTF-*)

| Method | Path | Permission |
|---|---|---|
| POST, GET | /tasks/{id}/recordings | POST: `recordings.create` + assigned moderator + task IN_PROGRESS (503 NOT_CONFIGURED without storage); body `{native_sample_rate, channel_count (captured, 1-8), device_channel_count (browser-reported or null), echo_cancellation, noise_suppression, auto_gain_control, device_label, user_agent}`; the response's `channel_handling` is set by the server (D-048); GET: task visibility |
| PUT | /recordings/{id}/chunks/{seq} | raw float32 body of whole frames (a multiple of 4 × channel_count bytes, else 422 INVALID_CHUNK), only real numbers (NaN or infinity: 422 INVALID_AUDIO), `X-Content-SHA256` header checked; same chunk again is accepted, a different one is 409 |
| POST | /recordings/{id}/interrupted | the recording's moderator; body `{reason}` |
| POST | /recordings/{id}/complete | the recording's moderator; body `{chunk_count}`; 409 MISSING_CHUNKS lists gaps; starts processing |
| POST | /recordings/{id}/discard | the recording's moderator; deletes uploaded chunks |
| GET | /recordings/{id} | task visibility; includes assets with the full validation record |
| POST | /assets/{id}/url | body `{purpose: play or download}`; play needs `recordings.view`, download `recordings.download`; signed link valid SIGNED_URL_SECONDS (300) |
| GET | /storage/usage | `dashboard.view` + `projects.manage` (D-049); files and bytes per managed project and asset kind |

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

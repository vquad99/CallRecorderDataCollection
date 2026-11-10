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
- Capacity (D-059): creating, importing or re-enabling an account beyond the staff-account capacity
  setting answers 409 `CAPACITY_REACHED` (details: limit, active, adding).
- Temporary outages (D-055): 503 `STORAGE_UNAVAILABLE` or `DATABASE_UNAVAILABLE` with `Retry-After: 5`;
  clients keep their data and try again (the recorder's uploader retries every 5xx).

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
| GET, PUT | /projects/{id}/languages, /audio-rules, /retention | member / `projects.manage` (guidelines withdrawn, D-062) |
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
| GET, POST | /tasks | `tasks.view` / `tasks.assign`; GET filters: project_id, status, mode, mine, search (task or participant code, D-057), page, page_size (at most 100) |
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

## Human transcription and transcript QC (TRN-*, TQC-*) - WITHDRAWN (D-062)

No endpoints: nobody transcribes or reviews transcripts by hand. AI transcripts (when a project turns
them on) are read with the recording.

## Exports (EXP-*)

| Method | Path | Permission |
|---|---|---|
| POST | /exports | `exports.create` (filters validated; personal data needs explicit grant) |
| GET | /exports/{id} | `exports.create` |
| POST | /exports/{id}/download-url | `exports.create` (short-lived; audited) |

## Dashboards (DASH-*)

| Method | Path | Permission |
|---|---|---|
| GET | /dashboard?project_id=&days=7..90 | `dashboard.view` (built 2026-11-10, D-065). Answer shaped by role: `view` = `client` (progress only: hours recorded / approved, daily targets, per mode, per day), `worker` (the same for the caller's own tasks and recordings, plus tasks by status and QC counts) or `manager` (whole projects, plus `queues`, `team` output per moderator and `storage_bytes`). Fields a view does not get are `null`. A project the caller cannot see answers 404 like a missing one. Days are calendar days in `REPORT_TIMEZONE`. |
| GET | /dashboard/productivity, /dashboard/failures, /dashboard/provider-usage | Phase 9: `dashboard.view`; filters: date range, language, dialect, mode, staff, status |

## Audit (SEC-*)

| Method | Path | Permission |
|---|---|---|
| GET | /audit-logs | `audit.view` |

## Security review changes (D-064)

- `POST /auth/mfa/enroll` takes `{"password": "..."}`; a wrong password answers 400 `INVALID_CREDENTIALS` and counts as a failed sign-in.
- `POST /auth/password/forgot` answers 202 at once for every address; the lookup and email happen afterwards.
- `GET /projects/{id}/members`: `email` is `null` unless the caller manages the team (`projects.members` in that project).
- `GET /projects/{id}/member-candidates?search=`: a Super Admin may search part of a name or email; anyone else gets a match only for a full email address, and Super Admins are never offered.

## Participant personal page (PART-013, PART-014, D-067)

| Method | Path | Access |
|---|---|---|
| POST | /projects/{id}/participants/{id}/portal-link | `participants.manage` in the project. Answers `{url, expires_at}` once; ends any earlier link. |
| DELETE | /projects/{id}/participants/{id}/portal-link | `participants.manage`. Ends the link. |
| GET | /portal/me | Public; header `X-Portal-Token`. The participant's code, project name, consent form and answer, own sessions, accepted minutes. 404 `LINK_INVALID` for any link that does not work. |
| POST | /portal/consent | Public; header `X-Portal-Token` and the CSRF token. Body `{decision: GIVEN / REFUSED / WITHDRAWN}`. 409 `NOTHING_TO_WITHDRAW`, 409 `CONSENT_FORM_MISSING`. |

Projects carry `consent_text` (up to 20 000 characters) beside `consent_policy_version`. In consent
history, `captured_by` is `null` for the participant's own answers.

| GET | /recordings/{id}/consent-form | `recordings.download` in the project and the task visible. A printable HTML consent record for the recording, as an attachment (D-068). |
| POST | /projects/{id}/participants/{id}/portal-link/email | `participants.manage`. Creates a fresh link and emails it to the participant; answers `{sent, expires_at}`; 409 `NO_EMAIL`. Participants carry `email` (contact viewers only) and `has_email`; create/correct accept `email` (omitted = keep, empty = remove). |
| POST | /projects/{id}/participants/import | `participants.manage`. `{csv, confirm}`; answers each row's result, `ready`, `created`. |
| POST | /projects/{id}/participants/bulk | `participants.manage`. `{action: assign / remove / send_consent, participant_ids (1-200), target_project_id?, reason?}`; answers each participant's result. |
| POST | /projects/{id}/participants/{id}/consent-review | `participants.manage`. `{decision: APPROVED / REJECTED, note}`; 409 `NOTHING_TO_REVIEW`, 422 `NOTE_REQUIRED`. Participants carry `consent_status`, `consent_review`, `link_active` for callers who may see consent. |
| GET | /projects/{id}/participants/{id}/consent-form | `consent.view`, same rule as consent history. The form text answered, version, current answer with review, earlier answers. |
| GET | /projects/{id}/participants/{id}/consent-form/file | Same access. The same as a printable HTML attachment (audited). |
| GET | /system/status | `settings.manage` (Super Admin only, D-075). `{status, checks, version}` for the System status page. |

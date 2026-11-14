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
| GET | /projects | member. Newest first (D-105) |
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

## Telephony (TEL-*) - built for TxContact (D-101, D-102, D-103); not yet tested on the account

The moderator is the TxContact agent: the platform asks TxContact to ring participant A and
connect them to the moderator's seat; the moderator adds B in TxContact's own screen. There are
no provider webhooks: after the call is closed the platform looks for its recording itself.

| Method | Path | Who | What |
|---|---|---|---|
| GET | /telephony/status | `tasks.view` | `{configured, provider}`; "Not configured" until the TxContact logins are set |
| GET | /tasks/{id}/calls | sees the task | The task's newest 20 calls, each with its checklist, candidates and history |
| POST | /tasks/{id}/calls | the assigned moderator (`calls.start`) | Rings A. Task must be telephony and In progress; the moderator needs an agent seat; a participant who refused consent is not called; at most `TELEPHONY_MAX_CALLS_PER_TASK_PER_HOUR` (6) calls an hour for a task (429 `TOO_MANY_CALLS`). 201 also when TxContact refused: the call is `DIAL_FAILED` with TxContact's answer |
| POST | /calls/{id}/checklist | `calls.end`; the task's moderator or a manager | `{item, done}`: A_JOINED, B_JOINED, MODERATOR_MUTED, QUALITY_OK |
| POST | /calls/{id}/close | same | Needs A_JOINED and B_JOINED ticked (409 `CHECKLIST_INCOMPLETE`) and consent Given for A and B (409 `CONSENT_MISSING`). The call waits for its recording |
| POST | /calls/{id}/cancel | same | `{reason, note}`: NO_ANSWER, WRONG_NUMBER, CALL_DROPPED, POOR_QUALITY, CONSENT_REFUSED, OTHER (note needed). Allowed at every stage before the recording is stored |
| POST | /calls/{id}/match | same | `{key}`: one of the listed candidates, when the platform could not tell which TxContact call is this one |
| POST | /calls/{id}/retry | same | Look for the recording again |
| PUT | /users/{id}/telephony-agent | `users.manage` | `{agent_id}`; one seat per person; empty removes it |
| GET | /telephony/analytics | `tasks.assign` | `?project_id&days` (1-90). Figures for the calls the caller may see: Super Admin all, Project Admin their projects. 403 for everyone else (D-104) |
| GET | /calls | `tasks.view` | `?project_id&state&page&page_size` (max 100). `state=NEEDS_PERSON`: needs a match, failed to fetch, or left open. Super Admin all, Project Admin their projects, moderators their own calls only |
| GET | /calls/export | `tasks.assign` | `?project_id&days`: the same calls as a CSV file (no phone numbers). Audited as `calls.exported`. 403 for everyone else (D-104) |
| GET | /telephony/provider-traffic | `tasks.assign` | TxContact's own calls per hour of the day; `available: false` with the reason when TxContact does not answer |

Call states: `DIALLING` (on the call), `DIAL_FAILED`, `CANCELLED`, `WAITING_FOR_RECORDING`,
`NEEDS_MATCH`, `FETCH_FAILED`, `RECORDED`. A provider's call id and file name are only ever shown
masked (a run of nine or more digits is cut to its last two): they may carry the caller's number.

`GET /tasks/{id}/recordings` returns each recording **with its files** (`assets`), so the task page
can offer Listen and the download (D-103; the page relied on this since D-092).
`GET /recordings/{id}/metadata` has a `call` section for a phone recording: provider, call
reference, agent seat, moderator, times, note, checklist, history.
`GET /projects/{id}/export?content=progress` has two more columns: `phone_calls`, `last_call_state`.

Not built (the specification's conference-by-API design; TxContact has no such API, D-101):
`/calls/{id}/add-b`, `/moderator/join`, `/moderator/leave`, `/mute`, `/webhooks/telephony/{provider}`,
`/admin/webhook-events`.

## Audio QC (AQC-*)

| Method | Path | Permission |
|---|---|---|
Built 2026-11-10 (D-079). The QC Executive's queue is the task list (`mine=true`, status AUDIO_QC).

| Method | Path | Permission |
|---|---|---|
| GET | /tasks/{id}/audio-qc | `tasks.view` and the task visible. Every automatic result with its checks, every decision, the assigned QC Executive and what the caller may do. |
| POST | /tasks/{id}/assign-qc | `tasks.assign` in the project. Body `user_id`, `reason` (required when reassigning). 422 NOT_PROJECT_MEMBER, NOT_A_QC_EXECUTIVE, SAME_PERSON; 409 TASK_LOCKED. |
| POST | /tasks/{id}/audio-qc/decision | `audio_qc.review` and the task's assigned QC Executive (Super Admin: any). Body `outcome` PASS / FAIL / RETURN, `reason_code`, `comment`. 409 TASK_NOT_IN_QC, NO_AUTOMATIC_CHECK; 422 REASON_REQUIRED, COMMENT_REQUIRED. |
| POST | /tasks/{id}/audio-qc/recheck | Manager of the project or the assigned QC Executive. Downloads the delivery file and checks its bytes. 503 STORAGE_UNAVAILABLE. |
| GET | /recordings/{id}/metadata | `recordings.download` in the project and the task visible. The details file (JSON attachment, format `ccp.recording-metadata/1`), audited. |

## AI transcription (ASR-*)

| Method | Path | Permission |
|---|---|---|
| GET | /transcription-jobs | `asr.view` (admin) |
| POST | /transcription-jobs/{id}/retry, /cancel | `asr.manage` |

## Human transcription and transcript QC (TRN-*, TQC-*) - WITHDRAWN (D-062)

No endpoints: nobody transcribes or reviews transcripts by hand. AI transcripts (when a project turns
them on) are read with the recording.

## Exports (EXP-*) - built (D-094, D-105)

All under `/projects/{id}` and for people with `exports.create` in the project (Super Admin,
Project Admin, Client Viewer). Recordings are exported as a bundle made in the background;
reports are one table each.

| Method | Path | What |
|---|---|---|
| GET | /projects/{id}/export/summary | `?content=audio/metadata/both&scope=approved/finished&mode&language&recorded_from&recorded_to&originals`: `{recordings, face_to_face, telephony, audio_bytes, file_name}` for that choice. 422 for a choice that makes no sense (unknown language, days the wrong way round, originals with metadata only) |
| GET | /projects/{id}/export | `?content=progress/participants&format=csv/tsv`: one report as a table, as an attachment. Audited as `project.exported` |
| POST | /projects/{id}/exports | `{content, scope, table_format, mode?, language?, recorded_from?, recorded_to?, originals?, contact?}`: 202 with the job (`QUEUED`). `originals` needs `projects.manage` and `contact` needs `participants.export` (403). 422 `NOTHING_TO_EXPORT`, `TOO_LARGE` (more than 5000 recordings); 409 `TOO_MANY_EXPORTS` (3 open per project). Audited as `export.requested` |
| GET | /projects/{id}/exports | `?page&page_size` (max 50), newest first |
| GET | /projects/{id}/exports/{job_id} | The job: `state` (QUEUED, RUNNING, READY, FAILED, EXPIRED), `recordings`, `files`, `size_bytes`, `sha256`, `error`, `expires_at`, `downloads`, `requested_by` |
| POST | /projects/{id}/exports/{job_id}/download-link | `{url, valid_seconds, file_name, sha256}`: a link that works for `SIGNED_URL_SECONDS` (300). The caller must be allowed to ask for the job's own choice (403). 409 `EXPORT_NOT_READY`, `EXPORT_EXPIRED`. Audited as `export.download_link` |
| DELETE | /projects/{id}/exports/{job_id} | Takes a READY bundle out of storage now, or withdraws a QUEUED one (state `EXPIRED`); 409 while it is being made. Audited as `export.removed` |

A bundle holds `face_to_face/` and `telephony/` (each with `audio/`, `originals/` when asked for,
`metadata/`, `consent/`), `recordings.csv` or `.tsv`, `recordings.json`, `participants.csv` or
`.tsv`, `schema/` (JSON Schemas: `ccp.export-recordings/1`, `ccp.export-manifest/1`,
`ccp.recording-metadata/1`), `README.txt`, `manifest.json`, `manifest.csv` and `SHA256SUMS`.
Tables are UTF-8 with a byte-order mark; a cell that starts with `=`, `+`, `-` or `@` has an
apostrophe put before it. No transcripts: this version makes none.

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
| GET | /projects/{id}/participants/{id}/details | `participants.manage` in the project (403 otherwise; D-104). Everything about the participant there: `participant` (as in the list), `updated_at`, `added_by`, `projects` (only those the caller may see), `removed` `{at, by, reason}`, `link` `{active, created_at, created_by, expires_at, last_used_at, handed_out}`, `consent_form` (as above), `minutes` (for people who may export), `calls` `{total, recorded, last_at, last_state}`, `sessions` (newest 200: `task_id, task_code, mode, slot, status, other_participant_code, moderator, consent_status, consent_method, consent_at, recordings, recording_seconds, recorded_at, phone_calls, created_at`) and `sessions_total`. |
| GET | /system/status | `settings.manage` (Super Admin only, D-075). `{status, checks, version}` for the System status page. |

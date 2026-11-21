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
- Request limits (D-052): bodies over MAX_REQUEST_BYTES (2.5 MB; audio chunks MAX_CHUNK_BYTES, 8 MB;
  a participant's document upload 10 MB, D-144) get 413 `PAYLOAD_TOO_LARGE`; a NUL character in the path, query string or a JSON body gets 422
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
| GET | /auth/me | authenticated. Carries `mfa_setup_required` (D-106), `session_idle_minutes` (D-122, D-125), and the user's own phone seat: `telephony_agent_id`, `telephony_has_password` (D-130; never the password) |
| GET | /auth/phone-seat/password | authenticated, own seat only. `{password}`: the saved password of the caller's phone seat; 404 when none is saved. Audited as `user.seat_password_shown` (D-130). `?purpose=line`: taken by the caller's page to sign the seat in to TxContact (D-133), audited as `user.phone_line_signed_in` instead |
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
| POST | /users/{id}/mfa/reset | `users.manage`. For a lost authenticator: two-step sign-in off and signed out everywhere; `{sessions_revoked}`. 409 `MFA_NOT_ENABLED`, `USE_ACCOUNT_PAGE` (one's own account). Audited as `user.mfa_reset` (D-106) |
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
| GET, PATCH | /projects/{id} | member / `projects.manage`. Includes `qc_final_approval` (default false; PATCH takes it): a QC pass approves the task with no admin review (D-138). Includes `max_conversations_per_speaker` (1 to 1000, default 3, null = no limit) and `unique_pairs` (default true); POST and PATCH take them (D-143). Includes `consent_mode` (`ONLINE`, default, or `UPLOAD`); POST and PATCH take it, audited with the project (D-144). Includes `speaker_min_age`, `speaker_max_age` (1 to 120, defaults 20 and 60) and `required_speaker_details` (default every speaker detail); POST and PATCH take them (D-145, below). Includes `qc_checklist`, the QC checklist (D-146, below; a PATCH that leaves it out keeps it) |
| POST | /projects/{id}/status | `projects.manage` (reopen needs reason) |
| GET, PUT | /projects/{id}/languages, /audio-rules, /retention | member / `projects.manage` (guidelines withdrawn, D-062) |
| GET, PUT | /projects/{id}/asr | member / `projects.manage` (AI transcription on/off, Deepgram settings; shows Not configured without a key) |
| GET, POST, DELETE | /projects/{id}/members | GET: `tasks.assign` in the project (Super Admin, Project Admin; 403 for others, D-112); POST/DELETE: `projects.members` |
| GET | /projects/{id}/member-candidates | `projects.members` (D-032) |

## Participants (PART-*)

| Method | Path | Permission |
|---|---|---|
| GET, POST | /projects/{id}/participants | `participants.manage` in the project for both (the whole list: Super Admin, Project Admin; 403 for others, D-112). Others see the participants of their own tasks on those tasks. POST answers the participant with `consent_email` (D-129). Rows carry the speaker details, `speaker_details_complete` and, for people with `tasks.assign`, `pairing` (D-143) |
| POST | /projects/{id}/participants/link | `participants.manage` (add an existing participant by code); answers with `consent_email` (D-129) |
| GET, PATCH | /projects/{id}/participants/{pid} | `participants.view` / `participants.manage` (corrections audited) |
| POST | /projects/{id}/participants/{pid}/delete | `participants.manage` (reason required; removes personal data) |
| GET | /projects/{id}/participants/{pid}/consent | `consent.view` + participant manager, or the moderator on an open task with that person (D-049); each participant row carries `consent_visible` |
| GET | /projects/{id}/participants/export | `participants.export` |
| GET | /projects/{id}/participants/{pid}/documents | People who manage participants, the moderator of an open task with the person, a QC Executive who decides the QC of a task with them; 403 for others in the project (D-144) |
| POST | /projects/{id}/participants/{pid}/documents/{kind} | `kind` `consent-form` (people who manage participants, the moderator of an open task with the person; Upload projects only) or `address-proof` (people who manage participants). The body is the file (D-144) |
| POST | /projects/{id}/participants/{pid}/documents/{document_id}/url | Whoever may see that kind (D-144): a short-lived link |

## Tasks (TASK-*)

| Method | Path | Permission |
|---|---|---|
| GET, POST | /tasks | `tasks.view` / `tasks.assign`; GET filters: project_id, status, mode, mine, search (task or participant code, D-057), page, page_size (at most 100). POST: both participants must have agreed to the project's consent form, else 422 `CONSENT_REQUIRED` naming them ("P000009 and P000010 have not agreed to this project's consent form yet.", `details[0].participants`, D-129), and be within the project's pairing rules: 422 `SPEAKER_DETAILS_MISSING`, 422 `SPEAKER_AGE_OUT_OF_RANGE` (D-145), 409 `SPEAKER_LIMIT_REACHED`, 409 `PAIR_ALREADY_USED` (D-143) |
| GET | /tasks/{id} | `tasks.view`. Includes `consent_missing` (`["A"]`, `["B"]`, both or empty): who has not agreed to the project's consent form (D-119, D-129), and `consent_mode`; each participant carries `consent_form` and `can_upload_consent_form` (D-144). At CONSENT_FIX, `consent_fix`: `{comment, by, at, participants: [{side, participant_id, participant_code, replaced}], forms_replaced, can_send_back}`, QC's send-back for a consent form (D-146); null otherwise |
| POST | /tasks/{id}/transition | depends on target (backend/app/modules/tasks/workflow.py); body `{to, reason_code, comment}`; platform-only targets refused (D-037). AUDIO_QC -> CONSENT_FIX only by the QC decision; CONSENT_FIX -> AUDIO_QC (the task's moderator or someone who assigns tasks) is the same as `POST /tasks/{id}/consent-fix/send-to-qc`; CONSENT_FIX -> CANCELLED by someone who assigns tasks (D-146) |
| POST | /tasks/{id}/assign | `tasks.assign` (reason required on reassignment); 409 `CONSENT_REQUIRED` while a participant has not agreed to the consent form (D-129) |
| POST | /tasks/{id}/comments | `tasks.view` |
| GET | /tasks/{id}/timeline | `tasks.view` (status history, assignments, comments). Status entries also carry `from_status`, `to_status`, `reason_code`, `comment` (null on other entries, D-125) |

## Storage and face-to-face recording (STOR-*, FTF-*)

| Method | Path | Permission |
|---|---|---|
| POST, GET | /tasks/{id}/recordings | POST: `recordings.create` + assigned moderator + task IN_PROGRESS + `native_sample_rate` equal to the project's face-to-face rate (422 `SAMPLE_RATE_NOT_ALLOWED`, D-123; at most 48000 Hz and 2 captured channels; a recording larger than `MAX_RECORDING_BYTES`, default 3 GB, gets 422 `TOO_LARGE`, D-124) + both participants have consent (409 `CONSENT_MISSING` with `details[0].missing`, D-119) (503 NOT_CONFIGURED without storage); body `{native_sample_rate, channel_count (captured, 1-8), device_channel_count (browser-reported or null), echo_cancellation, noise_suppression, auto_gain_control, device_label, user_agent}`; the response's `channel_handling` is set by the server (D-048); GET: task visibility. Each recording has `current`: the task's newest finished one, the one QC checks and an export delivers (D-135). People with `tasks.assign` in the project and the task's moderator get every recording; anyone else only the current one |
| PUT | /recordings/{id}/chunks/{seq} | raw float32 body of whole frames (a multiple of 4 × channel_count bytes, else 422 INVALID_CHUNK), only real numbers (NaN or infinity: 422 INVALID_AUDIO), `X-Content-SHA256` header checked; same chunk again is accepted, a different one is 409 |
| POST | /recordings/{id}/interrupted | the recording's moderator; body `{reason}` |
| POST | /recordings/{id}/complete | the recording's moderator; body `{chunk_count}`; 409 MISSING_CHUNKS lists gaps; starts processing |
| POST | /recordings/{id}/discard | the recording's moderator; deletes uploaded chunks |
| GET | /recordings/{id} | task visibility; includes assets with the full validation record and `current`. A replaced recording (not current) answers 404 for anyone but the project's managers and the task's moderator (D-135), as do its asset links, details file and consent record |
| POST | /assets/{id}/url | body `{purpose: play or download}`; play needs `recordings.view`, download `recordings.download`; signed link valid SIGNED_URL_SECONDS (300) |
| GET | /storage/usage | `dashboard.view` + `projects.manage` (D-049); files and bytes per managed project and asset kind |

## Telephony (TEL-*) - built for TxContact (D-101, D-102, D-103); not yet tested on the account

The moderator is the TxContact agent: the platform asks TxContact to ring participant A and
connect them to the moderator's seat; the moderator adds B in TxContact's own screen. There are
no provider webhooks: after the call is closed the platform looks for its recording itself.
The moderator's seat is signed in and kept Ready by their own page, at TxContact's agent
manager (a WebSocket, D-133); the API gives the page the settings and the seat password.

| Method | Path | Who | What |
|---|---|---|---|
| GET | /telephony/status | `tasks.view` | `{configured, provider, seat_login}`; "Not configured" until the TxContact logins are set. `seat_login` (D-133): how the caller's page signs their seat in, `{url, tenant_id, agent_id, extension, has_password}` with the caller's own seat (`agent_id` and `extension` null without one); null when phone calls are not configured or `TXCONTACT_SEAT_LOGIN` is off |
| GET | /tasks/{id}/calls | sees the task | The task's newest 20 calls, each with its checklist, candidates and history |
| POST | /tasks/{id}/calls | the assigned moderator (`calls.start`) | Rings A. Task must be telephony and In progress; the moderator needs an agent seat; nobody is called before both agreed to the consent form (409 `CONSENT_MISSING`); at most `TELEPHONY_MAX_CALLS_PER_TASK_PER_HOUR` (6) calls an hour for a task (429 `TOO_MANY_CALLS`). 201 also when TxContact refused: the call is `DIAL_FAILED` with TxContact's answer |
| POST | /calls/{id}/checklist | `calls.end`; the task's moderator or a manager | `{item, done}`: A_JOINED, B_JOINED, MODERATOR_MUTED, QUALITY_OK |
| POST | /tasks/{id}/delete | `tasks.assign` in the project | `{reason}`; 204. Only while nothing has happened on the task (409 `TASK_HAS_WORK` otherwise: cancel it instead). Audited as `task.deleted` (D-115) |
| POST | /calls/{id}/call-b | the task's moderator (`calls.start`) | Rings participant B into the call on the moderator's seat (D-111). 409 `A_NOT_JOINED` until A_JOINED is ticked, `CALL_STATE` when the call is not on; 429 `TOO_MANY_CALLS` after 3 rings. The call carries `b_dial_attempts`, `b_dialled_at`, `b_dial_status` (ACCEPTED, REFUSED, UNREACHABLE), `b_phone_hint` |
| POST | /calls/{id}/recording/start, /calls/{id}/recording/stop | the task's moderator | Marks where the conversation starts and stops (D-113). Start needs A_JOINED and B_JOINED (409 `CHECKLIST_INCOMPLETE`); Stop needs a start (409 `RECORDING_NOT_STARTED`). The call carries `record_started_at`, `record_stopped_at` |
| POST | /calls/{id}/close | same | Needs A_JOINED and B_JOINED ticked (409 `CHECKLIST_INCOMPLETE`) and consent Given for A and B (409 `CONSENT_MISSING`). The call waits for its recording |
| POST | /calls/{id}/cancel | same | `{reason, note}`: NO_ANSWER, WRONG_NUMBER, CALL_DROPPED, POOR_QUALITY, CONSENT_REFUSED, OTHER (note needed). Allowed at every stage before the recording is stored |
| POST | /calls/{id}/match | same | `{key}`: one of the listed candidates, when the platform could not tell which TxContact call is this one |
| POST | /calls/{id}/retry | same | Look for the recording again |
| PUT | /users/{id}/telephony-agent | `users.manage` | `{agent_id, password?}`; one seat per person; empty `agent_id` removes the seat and its password. `password` (D-130), stored encrypted: left out keeps the saved one, `""` removes it; a password without a seat is 422. Answers `{user_id, telephony_agent_id, has_password}`, never the password. `GET /users` and `/users/{id}` carry `telephony_has_password`. Audited as `user.agent_seat` without the password |
| GET | /users/{id}/telephony-agent/password | `users.manage`, Super Admin only | `{password}`: the saved seat password (D-130); 404 when none is saved. Audited as `user.seat_password_shown`. A user reads their own with `GET /auth/phone-seat/password` |
| GET | /telephony/analytics | `tasks.assign` | `?project_id&days` (1-90). Figures for the calls the caller may see: Super Admin all, Project Admin their projects. 403 for everyone else (D-104) |
| GET | /calls | `tasks.view` | `?project_id&state&page&page_size` (max 100). `state=NEEDS_PERSON`: needs a match, failed to fetch, or left open. Super Admin all, Project Admin their projects, moderators their own calls only |
| GET | /calls/export | `tasks.assign` | `?project_id&days`: the same calls as a CSV file (no phone numbers). Audited as `calls.exported`. 403 for everyone else (D-104) |
| GET | /telephony/provider-traffic | `tasks.assign` | TxContact's own calls per hour of the day; `available: false` with the reason when TxContact does not answer |

Call states: `DIALLING` (on the call), `DIAL_FAILED`, `CANCELLED`, `WAITING_FOR_RECORDING`,
`NEEDS_MATCH`, `FETCH_FAILED`, `RECORDED`. A provider's call id and file name are only ever shown
masked (a run of nine or more digits is cut to its last two): they may carry the caller's number.
Times from TxContact (a candidate's `start`, a phone recording's start and end) are real times:
TxContact's clock runs ahead, and every time it reports is moved back by
`TXCONTACT_CLOCK_AHEAD_MINUTES` (D-131).

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

**QC checklist answers (D-146).** `answers` is `{conversation: {key: "yes" | "no"}, speakers: {"A": {key: ...}, "B": {key: ...}}, consent: {"A": "yes" | "no", "B": ...}}` (A and B: the task's participants). A question left out, or null, is not answered; answers to questions not in the project's checklist are dropped; `consent` counts only in an UPLOAD project (the consent check: "Consent form checked: signed, the right person, this project"). Each decision keeps them on its result as `checklist`: `items` (the questions as they read then), `consent_check`, `conversation`, `participants` (`side`, `participant_id`, `participant_code`, `answers`, `consent`, `consent_form_id`: the form on file then) and `failing` (`{key, side, answer}`), so a checklist changed later does not change answers given.

| Method | Path | Permission |
|---|---|---|
| GET | /tasks/{id}/audio-qc | `tasks.view` and the task visible. Every automatic result with its checks, every decision, the assigned QC Executive and what the caller may do; `pass_approves`: a pass approves the task (the project's `qc_final_approval`, D-138). |
| GET | /tasks/{id}/audio-qc/checklist | `tasks.view` and the task visible. The QC checklist of the task (D-146): `items` (the project's checklist now), `consent_check` (true in an UPLOAD project: QC checks each signed form), `consent_question`, `can_answer` (the caller decides the task's QC and it is at AUDIO_QC), `draft` (`{answers, saved_at, saved_by_name}`, only for the person who decides; null for others or when none) and `latest` (the newest decision with answers: `outcome`, `reason_code`, `comment`, `reviewer_name`, `decided_at` and its stored checklist below; null when none). |
| PUT | /tasks/{id}/audio-qc/draft | The person who decides the task's QC (as for the decision), while it is at AUDIO_QC. Body: `answers` (below). Replaces the task's one draft, kept so a page reload keeps the ticks; answers `{answers, saved_at, saved_by_name}`. 403; 409 TASK_NOT_IN_QC. Not audited. |
| POST | /tasks/{id}/assign-qc | `tasks.assign` in the project. Body `user_id`, `reason` (required when reassigning). 422 NOT_PROJECT_MEMBER, NOT_A_QC_EXECUTIVE, SAME_PERSON; 409 TASK_LOCKED. Not needed normally: a task reaching AUDIO_QC is given by the platform to the project's active QC Executive with the fewest AUDIO_QC tasks, ties to the one given a task longest ago; never the moderator or a recorder; audited `task.qc_auto_assigned` with no actor (D-116). |
| POST | /tasks/{id}/audio-qc/decision | `audio_qc.review` and the task's assigned QC Executive (Super Admin: any). Body `outcome` PASS / FAIL / SEND_BACK_CONSENT (FAIL = reject; RETURN no longer accepted, D-118), `reason_code`, `comment`, `answers` (the QC checklist, D-146, below; left out = nothing answered). 409 TASK_NOT_IN_QC, NO_AUTOMATIC_CHECK, CONSENT_ONLINE (SEND_BACK_CONSENT in an ONLINE project); 422 REASON_REQUIRED, COMMENT_REQUIRED, and for PASS and SEND_BACK_CONSENT: CHECKLIST_INCOMPLETE (a required question unanswered) and CHECKLIST_FAILED (an answer equal to its question's `fails_on`), each naming the questions in `details[0].questions` ("P000123: Is speech intelligible?" for a speaker question). PASS in an UPLOAD project also needs both consent checks `yes` (422 CONSENT_NOT_CHECKED, CONSENT_NOT_OK). PASS moves the task to ADMIN_REVIEW, or to APPROVED where the project's `qc_final_approval` is on (history comment "Approved by the QC decision: QC pass is the final approval in this project." and the QC Executive's comment, D-138). FAIL takes whatever was answered. SEND_BACK_CONSENT (UPLOAD projects) needs a consent check `no` (422 CONSENT_NOT_MARKED) and a `comment` saying what is wrong with the form (422 COMMENT_REQUIRED); it moves the task to CONSENT_FIX (history "Consent form to fix: P000123. <comment>") and keeps the answers as the next draft with the consent check cleared; other decisions remove the draft. Audited `audio_qc.decision` with `failing` (keys; `A:key` for a speaker) and, for a send-back, `consent_to_fix` (codes). |
| POST | /tasks/{id}/audio-qc/recheck | Manager of the project or the assigned QC Executive. Downloads the delivery file and checks its bytes. 503 STORAGE_UNAVAILABLE. |
| POST | /tasks/{id}/consent-fix/send-to-qc | `tasks.view`; the task's moderator or someone who assigns tasks in the project (403 otherwise). Body `comment` (optional, at most 2000). Sends the same recording back to QC once every consent form QC marked `no` was replaced since the send-back (the current form is not the one QC saw; nothing to replace in a project switched back to ONLINE): 409 TASK_NOT_IN_CONSENT_FIX, CONSENT_FORM_NOT_REPLACED (`details[0].participants`), CONSENT_FIX_UNKNOWN (no send-back on record). The task goes to AUDIO_QC with its QC Executive; answers the task. Audited `audio_qc.consent_fixed` (participant codes, the new forms' ids, the send-back). D-146. |
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

One task's bundle (D-136):

| Method | Path | What |
|---|---|---|
| GET | /tasks/{id}/export | `exports.create` in the task's project and the task visible (Super Admin, Project Admin). A ZIP attachment made at once: the same folders and tables as a bundle above, for this task's current recording only (audio + metadata, approved tasks, CSV); name `both_<project>_<task>_<YYYYMMDD_HHMM>.zip`. 409 `TASK_NOT_APPROVED` before the task is approved, `NOTHING_TO_EXPORT` without a finished recording, `EXPORT_FAILED` when a stored file no longer matches its checksum; 503 without storage, and 503 `BUSY` when two are already being made in this server process (D-142). Audited as `task.exported` |

## Payments (D-137)

All under `/payments` and for people with `payments.manage` (Super Admin: every project; Project
Admin: their own). Moderators, QC Executives and Client Viewers get 403; a project the caller does
not run answers 404. Money and minutes are text with two places; rates are rupees per approved
minute.

| Method | Path | What |
|---|---|---|
| GET | /payments/rates | One row per project the caller runs: `{project_id, project_code, project_name, moderator_rate, participant_rate, updated_at, updated_by}` (a rate is null when not set) |
| PUT | /payments/rates/{project_id} | Body `{moderator_rate, participant_rate}`: null or 0 to 100000 with at most two decimals (422 otherwise). Audited as `payments.rates_changed` with before and after |
| GET | /payments/moderators | `?project_id&date_from&date_to&search`. APPROVED tasks only, by approval day in `REPORT_TIMEZONE`; one row per moderator and project: `{project_id, project_code, user_id, name, approved_tasks, approved_minutes, rate, amount}` (the full length of the tasks whose current recording they made). `search` matches the name. Answer `{timezone, date_from, date_to, totals: {count, minutes, amount, minutes_without_rate}, rows}`. 422 when the first day is after the last |
| GET | /payments/participants | The same filters; one row per participant and project: `{project_id, project_code, participant_id, participant_code, name, approved_sessions, payable_minutes, rate, amount}` (the participant's equal share; `name` only for people who manage participants in that project). `search` matches the code or the name |
| GET | /payments/moderators/export, /payments/participants/export | The same rows as CSV (UTF-8 with BOM, safe cells) with a Total line; `amount_inr` is `No rate set` where the project has no rate. Audited as `payments.exported` |

`amount` is null when the project has no rate for that kind of person. Minutes are rounded to two
places first; the amount is minutes x rate, rounded half up to the paisa. The current rate applies
to all approved work, including work approved before it was changed.

## Dashboards (DASH-*)

| Method | Path | Permission |
|---|---|---|
| GET | /dashboard?project_id=&days=7..90 | `dashboard.view` (built 2026-11-10, D-065). Answer shaped by role: `view` = `client` (progress only: hours recorded / approved, daily targets, per mode, per day), `worker` (the same for the caller's own tasks and recordings, plus tasks by status and QC counts) or `manager` (whole projects, plus `queues`, `team` output per moderator and `storage_bytes`; `queues.consent_forms_to_fix` counts the tasks at CONSENT_FIX, D-146). Fields a view does not get are `null`. A project the caller cannot see answers 404 like a missing one. Days are calendar days in `REPORT_TIMEZONE`. |
| GET | /dashboard (filters, D-108) | The same address takes `mode` (FACE_TO_FACE / TELEPHONY), `language`, `dialect`, `district` (D-121), `status` (a task status), `staff_id` (managers only, 403 otherwise) and `date_from` / `date_to` (days in the report time zone, at most 366; 422 when the first is after the last). Without chosen days the totals count everything and `daily` holds the last `days` days; with them every figure counts those days only and `daily` holds exactly them. The answer adds `options` (`languages`, `dialects`, `districts`, and for managers `staff` `[{id, name}]`), `date_from`, `date_to`, and for managers `calls` `{placed, recorded, could_not_be_placed, needs_a_person, open}`. Separate addresses for productivity, failures and provider usage are not built: this one carries them |

## Audit (SEC-*)

| Method | Path | Permission |
|---|---|---|
| GET | /audit-logs | `audit.view` |

## Security review changes (D-064)

- **Two-step sign-in is required for Super Admin and Project Admin (D-106).** While such an account has not set it up, every request answers 403 `MFA_SETUP_REQUIRED` except `GET /auth/me`, `POST /auth/mfa/enroll`, `POST /auth/mfa/confirm` and `POST /auth/logout`. `POST /auth/login` and `GET /auth/me` answer with `mfa_setup_required: true`. Setting: `REQUIRE_ADMIN_MFA` (unset: on everywhere except development and test).
- `POST /auth/mfa/enroll` takes `{"password": "..."}`; a wrong password answers 400 `INVALID_CREDENTIALS` and counts as a failed sign-in.
- `POST /auth/password/forgot` answers 202 at once for every address; the lookup and email happen afterwards.
- `GET /projects/{id}/members`: `email` is `null` unless the caller manages the team (`projects.members` in that project).
- `GET /projects/{id}/member-candidates?search=`: a Super Admin may search part of a name or email; anyone else gets a match only for a full email address, and Super Admins are never offered.

## Participant personal page (PART-013, PART-014, D-067)

| Method | Path | Access |
|---|---|---|
| DELETE | /projects/{id}/participants/{id}/portal-link | `participants.manage`. Ends the link. |
| GET | /portal/me | Public; header `X-Portal-Token`. The participant's code, project name, consent form and answer, own sessions, accepted minutes. 404 `LINK_INVALID` for any link that does not work. |
| POST | /portal/consent | Public; header `X-Portal-Token` and the CSRF token. Body `{decision: GIVEN / REFUSED}`; WITHDRAWN is refused (422). The answer counts at once (D-129). The same answer again changes nothing; any other answer after GIVEN gets 409 `ALREADY_AGREED`; 409 `CONSENT_FORM_MISSING`. |

Projects carry `consent_text` (up to 20 000 characters) beside `consent_policy_version`. In consent
history, `captured_by` is `null` for the participant's own answers.

| GET | /recordings/{id}/consent-form | `recordings.download` in the project and the task visible. A printable HTML consent record for the recording, as an attachment (D-068). |
| POST | /projects/{id}/participants/{id}/portal-link/email | `participants.manage`. Creates a fresh link and emails it to the participant; answers `{sent, expires_at}`; 409 `NO_EMAIL`; 409 `EMAILED_RECENTLY` within 10 minutes of the last email of this project's link (D-142; joining, import and bulk rows say "Emailed less than 10 minutes ago: not sent again."). A link whose email could not be sent is ended at once. Staff never get the link itself: the old `POST .../portal-link` that answered `{url}` is removed (405, D-142). Participants carry `email` (contact viewers only) and `has_email`; create/correct accept `email` (omitted = keep, empty = remove). |
| POST | /projects/{id}/participants/import | `participants.manage`. `{csv, confirm}`; columns `name,phone,email,language,dialect[,district]` and the speaker details (D-143); answers each row's result, `ready`, `created`; an added row's message says what happened to the consent form email (D-129). Participants carry `district` (free text, at most 100) on create, correct and read (D-121) |
| POST | /projects/{id}/participants/bulk | `participants.manage`. `{action: assign / remove, participant_ids (1-200), target_project_id?, reason?}`; answers each participant's result (an assigned one's message says what happened to the other project's consent form email, D-129). Participants carry `consent_status` (their answer as it counts now; `NONE` = no answer yet) and `link_active` for callers who may see consent. |
| GET | /projects/{id}/participants/{id}/consent-form | `consent.view`, same rule as consent history. The form text answered, version, current answer, earlier answers. |
| GET | /projects/{id}/participants/{id}/consent-form/file | Same access. The same as a printable HTML attachment (audited). |
| GET | /projects/{id}/participants/{id}/details | `participants.manage` in the project (403 otherwise; D-104). Everything about the participant there: `participant` (as in the list), `updated_at`, `added_by`, `projects` (only those the caller may see), `removed` `{at, by, reason}`, `link` `{active, created_at, created_by, expires_at, last_used_at, handed_out}`, `consent_form` (as above), `minutes` (for people who may export), `calls` `{total, recorded, last_at, last_state}`, `sessions` (newest 200: `task_id, task_code, mode, slot, status, other_participant_code, moderator, recordings, recording_seconds, recorded_at, phone_calls, created_at`) and `sessions_total`. |
| GET | /system/status | `settings.manage` (Super Admin only, D-075). `{status, checks, version}` for the System status page. Also `alerts` `{email_configured, recipients, active: [{code, summary, count, since}]}`: what the platform found wrong with itself at its last look (D-109). |

## Request guard (D-124)

A POST, PUT, PATCH or DELETE under `/api/v1/` without the session cookie gets 401, and one without the CSRF cookie or `X-CSRF-Token` header gets 403 `CSRF_FAILED`, **before its body is read**. Only `/auth/login`, `/auth/password/forgot`, `/auth/password/reset` (also invitation accept) and `/portal/consent` work without a session. Large bodies are read at most 16 at a time per process; a request that waits more than 15 s gets 503 `BUSY`. nginx limits `/api/` to 30 requests/s per address (burst 120) and chunk uploads to 5/s (burst 30, slowed rather than refused), with a JSON 429 when exceeded. Every list's `page` is at most 10 000. `TaskDetail` carries `can_reassign`; participants carry `phone_masked` (D-125). The task status `RETURNED` no longer exists (D-118, migration 0026): sending it gives 422.

## The page's own requests (D-141)

A request with the header `X-Background-Request: 1` (the page's own polling: a phone call or an export being prepared) is answered as usual but does not count as use: it does not move the session's idle clock (`last_seen_at`), so a session left open still ends after `session_idle_minutes` without the person's own requests (D-140). The header is optional and changes nothing else.

## Consent on tasks (D-127)

Each participant in `GET /tasks/{id}` carries `consent_status` and `consent_at` (their answer on the project's consent form as it counts now, D-129) and `may_record`. `POST /tasks/{id}/calls` answers 409 `CONSENT_MISSING` until both have agreed.

## Consent sent by itself, accepted at once (D-129)

Everyone who joins a project (added, added from a file, added as an existing participant, assigned in bulk) is emailed a fresh personal link to that project's consent form after the answer (`portal.send_links`, by the worker when there is one). The answer says what happened in `consent_email` (add, link) or the row's `message` (import, bulk assign): `Consent form emailed.`, `Write the project's consent form, then send it.` (the project has no consent form: nothing is sent), `No email address: add one with Edit, then email the consent form.`, or `The consent form could not be emailed now: use Email consent form again.` `POST .../portal-link/email` is the one manual resend. A participant's own "agree" counts at once; there is no review and no withdrawing. Removed: `POST /projects/{id}/participants/{pid}/consent-review`, the bulk action `send_consent`, `POST /tasks/{id}/consent` (consent noted by a moderator; older ones stay in the consent history) and the `consent.capture` permission (migration 0027). An "agree" that staff sent back before D-129 does not count as agreed.

## Participants need an email (D-128)

`POST /projects/{id}/participants` and `PATCH .../participants/{pid}` answer 422 `EMAIL_REQUIRED` without an email (a PATCH that leaves `email` out keeps the stored one; an empty one is refused). File imports need an `email` on every row. Task participants also carry `display_label` and `has_email`.

## Bulk consent form again (D-139)

`POST /projects/{id}/participants/bulk` also takes `action: send_consent`: everyone listed who has not agreed gets this project's consent form again (in the background); people who agreed get `ok: false` with "Already agreed: no form sent".

## Speaker details and pairing rules (D-143)

**Speaker details.** Participants carry these fields on create (`POST /projects/{id}/participants`), correct (`PATCH .../participants/{pid}`), list rows, `GET .../participants/{pid}` and `.../details`. Each may be null (people saved before D-143 have none); a value that is given is checked, else 422 `INVALID_SPEAKER_DETAILS` with the message and `details: [{"field": "<name>"}]`:

| Field | Value |
|---|---|
| `age` | whole number, 1 to 120 (any person); in a project, also within its speaker ages (D-145) |
| `gender` | `MALE`, `FEMALE` |
| `current_state`, `native_state`, `recording_state` | one of the 28 states and 8 union territories of India, written in full (any case; answered as the list writes it) |
| `current_district`, `recording_district` | free text, at most 100 |
| `district` | the native district (D-121): free text, at most 100; empty string when not given |
| `current_pincode`, `native_pincode`, `recording_pincode` | 6 digits, the first not 0 (spaces are dropped) |
| `native_language` | free text, at most 50 (e.g. `Konkani`) |
| `education` | `PRIMARY`, `SECONDARY`, `HIGHER_SECONDARY`, `DIPLOMA`, `BACHELORS`, `MASTERS`, `PHD`, `OTHER` |
| `education_medium` | `ENGLISH`, `NON_ENGLISH` |

Codes are taken in any case, with spaces or hyphens for underscores (`higher secondary`, `non-english`). On PATCH a field left out keeps its stored value; null (or an empty string) removes it. They are shown like the name: to people who manage participants in the project and to the moderator of an open task with the person; everyone else gets null, except `district` (shown as before). Every row also carries `speaker_details_complete` (every field the project needs is given: its `required_speaker_details`, D-145), for everyone who sees the row. Removing a participant removes them. The correction's audit entry names the fields that changed (`speaker_details_changed`), not their values.

**File import.** `POST .../participants/import` takes, after `district`, the columns `age,gender,current_state,current_district,current_pincode,native_state,native_pincode,native_language,education,education_medium,recording_state,recording_district,recording_pincode` (any of them may be left out of the file or empty). A value that is given is checked as above (the age also against the project's speaker ages, D-145) and a wrong one fails its row with the same message. A row without every detail the project needs is added; its message says `Ready to add (speaker details missing: add them with Edit before making tasks)` and `Added (...)`.

**Project options.** `projects.max_conversations_per_speaker` (integer 1 to 1000, default 3, null = no limit) and `projects.unique_pairs` (boolean, default true) on `GET`, `POST` and `PATCH /projects/{id}` (migration 0033 gives every existing project 3 and true). A PATCH that leaves them out sets the defaults, like the other project fields.

**Task rules.** `POST /tasks` and every row of `POST /tasks/import` (the check counts the rows above it) refuse, in this order:

| Code | Status | When |
|---|---|---|
| `SPEAKER_DETAILS_MISSING` | 422 | A participant lacks a speaker detail the project needs (D-145): "Participant P000123 has no complete speaker details yet: add them with Edit." (`details[0].participants`) |
| `SPEAKER_AGE_OUT_OF_RANGE` | 422 | A participant's age is outside the project's speaker ages (D-145): "Participant P000123 is outside this project's speaker ages (20 to 60)." (`details[0].participants`, `min_age`, `max_age`) |
| `SPEAKER_LIMIT_REACHED` | 409 | A participant already has `max_conversations_per_speaker` conversations in the project: "Participant P000123 already has 3 conversations in this project, the most for one speaker." (`details[0].participants`, `details[0].limit`) |
| `PAIR_ALREADY_USED` | 409 | With `unique_pairs`, the two (either way round) already share a task: "P000123 and P000124 already have a conversation together in this project (T000045): each pair of speakers only once." (`details[0].participants`, `details[0].task`) |

A conversation counts while its task is not `CANCELLED` or `REJECTED`; a deleted task counts for nothing. Tasks made before stay as they are.

**Pairing on the list.** For callers with `tasks.assign` in the project, each row of `GET /projects/{id}/participants` carries `pairing: {conversations, paired_with}`: the conversations that count toward the limit, and the ids of the participants they already share one with. Null elsewhere (one participant's own answer, other callers).

## Consent online or by upload, and participant documents (D-144)

**Project option.** `projects.consent_mode`: `ONLINE` (default; every project made before) or `UPLOAD`, on `GET`, `POST` and `PATCH /projects/{id}` (a PATCH that leaves it out sets `ONLINE`, like the other project fields; another value is 422). In an `UPLOAD` project nothing is emailed: `consent_email` on add and link, and the row messages of a file and of a bulk assignment, say "This project takes a signed consent form uploaded by staff: no consent form is emailed. Upload it with Documents."; `POST .../participants/{pid}/portal-link/email` and `POST .../participants/bulk` with `action: send_consent` answer 409 `CONSENT_BY_UPLOAD` with the same words.

**Consent that counts.** In an `UPLOAD` project a participant whose current signed consent form for the project is uploaded counts as having agreed, for `POST /tasks`, `POST /tasks/import`, `POST /tasks/{id}/assign`, calls and the recorder; an online "I agree" still counts too. Participant rows (`consent_status`) and task parties (`consent_status`, `consent_at` = when it was uploaded) then read `UPLOADED`. A form counts only while the project is `UPLOAD`. `CONSENT_REQUIRED` says "P000009 has no signed consent form uploaded in this project yet." The recording details file's `consent_form_answer` (and the export's `participant_a_consent`, `participant_b_consent`) may be `UPLOADED`.

**Rows.** Participant rows carry `has_consent_form` (this project's signed form is uploaded) and `has_address_proof`, for people who manage participants; null for others. `GET /tasks/{id}` carries `consent_mode` and, on each participant in an `UPLOAD` project, `consent_form` (the document below, for people who may see it; null otherwise) and `can_upload_consent_form`.

**Who.** People who manage participants in the project (Super Admin, Project Admin): both kinds. The moderator of an open task (not `APPROVED`, `REJECTED` or `CANCELLED`) with the participant: view, upload and replace the project's consent form. A QC Executive who decides the QC of a task with the participant: view the consent form. Others in the project: 403; a project the caller is not in, a participant not in the project, or a document of another participant or project: 404. A document of a kind the caller may not see answers 404 like one that does not exist.

`GET /projects/{id}/participants/{pid}/documents` answers:

| Field | Value |
|---|---|
| `consent_mode` | the project's |
| `consent_form`, `address_proof` | the current one (below) or null (none, or a kind the caller may not see) |
| `earlier` | replaced ones of the kinds the caller may see, newest first |
| `may_view_address_proof`, `may_upload_consent_form`, `may_upload_address_proof` | what the caller may do now (no consent form upload in an `ONLINE` project, nothing for a removed participant) |
| `max_bytes` | 10485760 |

A document: `{id, kind (CONSENT_FORM, ADDRESS_PROOF), file_name, content_type, size_bytes, sha256, uploaded_by, uploaded_at, replaced_by, replaced_at}` (`uploaded_by`, `replaced_by` are names).

`POST /projects/{id}/participants/{pid}/documents/{kind}` (`consent-form` or `address-proof`): the body is the file itself, its name percent-encoded in `X-File-Name` (at most 200 characters are kept; no name gives `consent_form.pdf` and the like). Answers 201 with the document; the current one of that kind (per project for a consent form) is marked replaced. Refusals:

| Code | Status | When |
|---|---|---|
| `INVALID_FILE_TYPE` | 422 | Not a PDF, JPEG or PNG by its first bytes (`%PDF-`, `FF D8 FF`, `89 50 4E 47 0D 0A 1A 0A`), whatever its name or `Content-Type`: "Only PDF, JPEG or PNG files can be uploaded, and this file is none of them. ..." |
| `INVALID_FILE` | 422 | An empty file |
| `PAYLOAD_TOO_LARGE` | 413 | Over 10 MB (10485760 bytes): "The file is larger than 10 MB. Scan it again at a lower resolution, or save it as a smaller PDF." |
| `CONSENT_ONLINE` | 409 | A consent form in an `ONLINE` project |
| `PARTICIPANT_DELETED` | 409 | The participant was removed |
| `STORAGE_UNAVAILABLE` / `NOT_CONFIGURED` | 503 | Storage failed / is not set up |

`POST /projects/{id}/participants/{pid}/documents/{document_id}/url` answers `{url, expires_in}`: a signed link to the file that shows it in the browser (no download name), valid `SIGNED_URL_SECONDS`.

**Audit.** `participant.document_uploaded` or `participant.document_replaced` (the replaced document's id and SHA-256 in `before`), and `participant.document_view_link`; with the kind, type, size and SHA-256, never the file or its name. Removing a participant (`participant.deleted`, with `address_proofs_removed`) deletes their address proofs from storage; their signed consent forms stay.

## Project rules (D-145)

What a client asks of a project is the project's own setting; the first client's numbers are only the defaults. All are on `GET`, `POST` and `PATCH /projects/{id}` (a PATCH takes the whole project: a field left out takes its default, like the other project fields) and are audited with the project (`project.updated`, before and after). The Rules tab edits them; Overview sends them back as they are.

| Field | Value |
|---|---|
| `speaker_min_age`, `speaker_max_age` | whole numbers, 1 to 120; defaults 20 and 60 (migration 0035 gives every existing project these). A youngest above the oldest: 422 `INVALID_AGE_RANGE` "The youngest speaker age (61) is above the oldest (60)" (`details[0].field`: `speaker_min_age`); outside 1 to 120: 422 `VALIDATION_ERROR` |
| `required_speaker_details` | the speaker details a person needs before a task: names of the fields in the speaker details table above (`age`, `gender`, `current_state`, `current_district`, `current_pincode`, `native_state`, `district`, `native_pincode`, `native_language`, `education`, `education_medium`, `recording_state`, `recording_district`, `recording_pincode`); default all of them; may be empty. Answered once each, in that order. Another name: 422 `UNKNOWN_SPEAKER_DETAIL` "shoe_size is not a speaker detail. Choose from: ..." |
| `max_conversations_per_speaker`, `unique_pairs` | as in D-143 |
| `consent_mode` | as in D-144 |
| `qc_final_approval` | as in D-138 |
| `qc_checklist` | D-146: the QC checklist, at most 60 `{key, question, scope, fails_on, required}`: `key` lowercase snake_case (`speech_intelligible`), at most 50, each once; `question` at most 200 (spaces tidied); `scope` `conversation` (answered once) or `speaker` (answered for each participant); `fails_on` `yes`, `no` or null (an observation: recorded, never failing); `required` (default true). Default the first client's 28 (13 conversation questions failing on `no`, 15 speaker observations; migration 0036 gives every existing project these). Unlike the fields above, a PATCH that leaves it out (or sends null) keeps the project's own. A wrong key, a key used twice or an empty question: 422 `INVALID_QC_CHECKLIST` "QC checklist, item 2: the key ok is used twice" (`details[0]`: `field`, `item`); a wrong shape, length or count: 422 `VALIDATION_ERROR`. The audit entry carries it only when it changed |

**The ages.** A participant's `age` may be 1 to 120. Where a project is known it must also be within that project's ages, else 422 `SPEAKER_AGE_OUT_OF_RANGE`:

- `POST /projects/{id}/participants` and `PATCH .../participants/{pid}` when the age changes (an age sent as it is stored is not checked again: it may have been saved in another project): "Age must be from 20 to 60 in this project (its speaker ages)", `details: [{"field": "age", "min_age": 20, "max_age": 60}]`;
- each row of `POST .../participants/import` (the row fails with the same message);
- `POST .../participants/link` and each participant of `POST .../participants/bulk` with `action: assign` (checked against the target project; `GET .../participants/link-candidates` leaves out people outside the ages): "Participant P000123 is outside this project's speaker ages (20 to 60).", `details: [{"participants": [...], "min_age", "max_age"}]` (their age is not told);
- `POST /tasks` and each row of `POST /tasks/import`, for both people, after `SPEAKER_DETAILS_MISSING` and before `SPEAKER_LIMIT_REACHED`.

No age is not checked here: when `age` is needed, `SPEAKER_DETAILS_MISSING` says so at task time.

**Complete.** `speaker_details_complete` on participant rows, `SPEAKER_DETAILS_MISSING` and a file row's `(speaker details missing: ...)` are judged against the project's `required_speaker_details`, so the same person may be complete in one project and not in another.

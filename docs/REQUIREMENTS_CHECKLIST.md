# Requirements checklist

GENERATED from docs/BUILD_STATUS.md by `python tools/requirements_checklist.py`;
do not edit by hand. Change the requirement's row in BUILD_STATUS.md, then regenerate.

333 requirements. Of the 290 that describe the product (not withdrawn, not a
process rule), 189 are built with passing automated tests (69 of them also verified) - 65 %.

| State | Count | Meaning |
|---|---:|---|
| Verified | 69 | built, automated tests pass and checked by hand or accepted at a gate |
| Built | 120 | built and automated tests pass; not yet checked by hand |
| Partly built / needs testing | 34 | some of it is built, or it needs a test that is not done yet |
| Needs fixing | 0 | built but a test fails |
| Not built | 20 | not started |
| Blocked | 47 | waiting on a decision or account from the owner or client (see Note) |
| Withdrawn | 20 | removed by an owner decision (see Note) |
| Process rule | 23 | how the work is done (GEN, PROC), not a feature of the app |

## By module

| Module | Verified | Built | Partly built / needs testing | Needs fixing | Not built | Blocked | Withdrawn | Process rule |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GEN |  |  |  |  |  |  |  | 14 |
| PROC |  |  |  |  |  |  |  | 9 |
| PROD |  | 1 | 2 |  | 1 |  |  |  |
| CAP |  | 3 |  |  |  | 2 |  |  |
| ARCH | 1 | 3 |  |  |  | 1 |  |  |
| FND | 13 | 16 |  |  |  |  |  |  |
| DB |  | 3 | 3 |  |  |  |  |  |
| ROLE | 5 | 6 |  |  |  |  | 1 |  |
| AUTH | 6 | 10 |  |  |  |  |  |  |
| USER | 3 | 6 |  |  |  |  |  |  |
| PROJ | 1 | 10 | 1 |  |  |  | 1 |  |
| PART | 7 | 10 |  |  |  |  |  |  |
| TASK | 8 | 4 |  |  |  |  |  |  |
| STOR | 4 | 8 | 1 |  |  |  |  |  |
| FTF | 13 |  | 2 |  |  |  |  |  |
| AUDIO | 8 | 1 | 2 |  |  | 13 |  |  |
| TEL |  | 9 | 11 |  |  | 18 |  |  |
| AQC |  | 8 | 2 |  |  |  |  |  |
| ASR |  |  |  |  | 10 |  |  |  |
| TRN |  |  |  |  |  |  | 12 |  |
| TQC |  |  |  |  |  |  | 6 |  |
| EXP |  | 8 | 2 |  |  |  |  |  |
| DASH |  | 4 | 1 |  |  | 1 |  |  |
| SEC |  | 10 | 2 |  |  | 3 |  |  |
| PWA |  |  |  |  | 9 |  |  |  |
| OPS |  |  | 3 |  |  | 6 |  |  |
| LOAD |  |  | 2 |  |  | 3 |  |  |

## GEN

| ID | State | Requirement | Note |
|---|---|---|---|
| GEN-001 | Process rule | Specification and runbook are the binding contract; the whole runbook is read before code changes; no module skipped, silently removed or silently changed. | Ongoing every phase |
| GEN-002 | Process rule | No fake data, mocked success, dummy buttons, placeholder pages, stub methods, TODO, FIXME or NotImplemented in production paths or in any feature marked complete; mocks only in isolated tests. | Ongoing every phase |
| GEN-003 | Process rule | A module is complete only when code exists, the app runs, the feature works, automated tests pass, the manual checklist passes and evidence is in BUILD_STATUS.md. |  |
| GEN-004 | Process rule | A blocked requirement is marked BLOCKED with evidence; provider-independent parts are built behind an adapter or marked boundary; an unconfigured external service shows a truthful Not configured state; nothing pretends to work. |  |
| GEN-005 | Process rule | No invented telephony endpoints, provider features, prices, compliance permissions, audio formats or model capabilities; official documentation URL, access date, feature and test evidence saved in docs/integrations/. |  |
| GEN-006 | Process rule | Evidence per module in docs/evidence/ (files, migrations, API routes, UI routes, tests and results, manual steps and results, screenshots where useful, defects, remaining work, commit hash); no real personal data or secrets in evidence. |  |
| GEN-007 | Process rule | A test not run is reported NOT RUN with the reason and its requirement is not marked verified; unfinished work is INCOMPLETE; undocumented provider claims are NOT VERIFIED. |  |
| GEN-008 | Process rule | No failing tests reported as success; no swallowed exceptions - errors are logged and surfaced. | Ongoing every phase |
| GEN-009 | Process rule | Existing working code preserved (no delete or rewrite without reason and approval); one small task at a time; when context or time runs out, save state, update the tracker and stop at a clean checkpoint. |  |
| GEN-010 | Process rule | After each task: format, lint, type-check, test, inspect the diff, update the tracker. | Ongoing every phase |
| GEN-011 | Process rule | Requirement IDs appear in the tracker, in tests, and in code comments where useful. | Ongoing every phase |
| GEN-012 | Process rule | Status vocabulary only: NOT STARTED, IN PROGRESS, BLOCKED, IMPLEMENTED — TESTS FAILING, IMPLEMENTED — AUTOMATED TESTS PASS, VERIFIED, ACCEPTED; VERIFIED needs automated and manual verification; ACCEPTED needs gate approval. | Ongoing every phase |
| GEN-013 | Process rule | No 'fully done' style claims unless the relevant acceptance gate has passed. |  |
| GEN-014 | Process rule | All applicable automated test layers exist: unit, API, database, integration (isolated test doubles), contract (provider mapping against documented schemas), audio fixtures, frontend, end-to-end, security, load; screenshots never replace integration tests. |  |

## PROC

| ID | State | Requirement | Note |
|---|---|---|---|
| PROC-001 | Process rule | Phases run in order; the next phase starts only after the current gate passes; no gate skipped. |  |
| PROC-002 | Process rule | Phase 0 documentation: REQUIREMENTS, REQUIREMENT_TRACEABILITY, ARCHITECTURE, DATABASE, API_CONTRACT, SECURITY, AUDIO_SPECIFICATION, TELEPHONY_PROVIDER_EVALUATION, TEST_PLAN, BUILD_STATUS, DECISIONS, TECH_STACK, DEPLOYMENT, integrations/, evidence/. |  |
| PROC-003 | Process rule | Phase 0 inspection commands (pwd, ls -la, find, git status --short, git log -5 --oneline) run and recorded; manifests, dependency files, Docker files, env examples, migrations, tests, CI and deployment config inspected; secret values never printed. |  |
| PROC-004 | Process rule | Traceability rows hold ID, requirement, phase, database, API, UI, test, status, evidence. |  |
| PROC-005 | Process rule | BUILD_STATUS.md has one row per module and one per requirement (Requirement ID, Description, Phase, Backend, Database, Frontend, Automated test, Manual test, Evidence path, Status, Blocker); every checkbox links to real evidence or stays unchecked; updated every session. | Ongoing every phase |
| PROC-006 | Process rule | End of every session: git status --short, git diff --check, relevant tests, tracker update, remaining work recorded; commit only if the owner's workflow permits. |  |
| PROC-007 | Process rule | Report after every session/phase in the required format (runbook A2 fields, spec 17 items), with exact commands and files. |  |
| PROC-008 | Process rule | Ask only for truly blocking decisions or credentials; owner approval before major architectural changes or deleting code; stop after Phase 0 and request approval. |  |
| PROC-009 | Process rule | Project called complete or production-ready only when the definition of done (spec 15) and every final release checklist item (runbook R) are met. |  |

## PROD

| ID | State | Requirement | Note |
|---|---|---|---|
| PROD-001 | Partly built / needs testing | One cloud-hosted, responsive web application used through a browser. | Runs as a web application; cloud hosting waits for B-04 |
| PROD-002 | Not built | Installable as a PWA from the browser's install option. | PWA in Phase 10 |
| PROD-003 | Built | No native Android or iOS app; participants install nothing; no physical GSM gateway. |  |
| PROD-004 | Partly built / needs testing | Two recording modes - telephony and face-to-face - with assets in separate folders/prefixes. | Face-to-face prefix built; telephony prefix with telephony (B-01) |

## CAP

| ID | State | Requirement | Note |
|---|---|---|---|
| CAP-001 | Built | Capacity settings (50 staff, 50 concurrent conferences, 2 participants, 250 h/day, 125 h/day each mode, cloud, web + PWA) stored as editable configuration, not source constants. |  |
| CAP-002 | Built | An administrator changes targets without a code deployment. |  |
| CAP-003 | Built | Languages configurable per project. |  |
| CAP-004 | Blocked | Capacity is proven only by a load test plus provider-side concurrency confirmation; never from a local or mock test. | Production load test and provider confirmation (B-01, B-04) |
| CAP-005 | Blocked | Storage sizing: 115.2 MB/h mono, 230.4 MB/h stereo, 43.2 GB/day at target, 1.296 TB/30 days, about 15.77 TB/year, excluding originals, backups, replicas, metadata and derived copies; retention confirmed before final sizing. | Retention periods (B-05) decide the sizing |

## ARCH

| ID | State | Requirement | Note |
|---|---|---|---|
| ARCH-001 | Built | Modular monolith first; no unnecessary microservices. |  |
| ARCH-002 | Built | Stack: React + TypeScript, FastAPI, PostgreSQL, Alembic, Celery + Redis, FFmpeg + a tested Python audio library, private S3-compatible storage, Docker, Nginx or managed ingress, web manifest + service worker; Pytest, Vitest/React Testing Library, Playwright; unless the repository already has a functioning equivalent. |  |
| ARCH-003 | Built | Stable versions pinned and recorded in docs/TECH_STACK.md. |  |
| ARCH-004 | Blocked | Cloud region chosen for data residency, latency and client requirements; recorded as a decision. | Hosting region (B-04) |
| ARCH-005 | Verified | Repository inspected before choosing or changing frameworks. |  |

## FND

| ID | State | Requirement | Note |
|---|---|---|---|
| FND-001 | Verified | Backend layout: app/main.py, core/{config,logging,security,errors}.py, api/router.py, db/{base,session}.py, db/migrations/, modules/, tests/, pyproject.toml, Dockerfile. |  |
| FND-002 | Built | FastAPI application factory. |  |
| FND-003 | Verified | Configuration from environment variables; required variables validated at startup; invalid configuration prevents unsafe startup. |  |
| FND-004 | Verified | Structured JSON logging with request IDs and no secrets. |  |
| FND-005 | Verified | Request ID middleware. |  |
| FND-006 | Built | Global exception handlers. |  |
| FND-007 | Verified | /health/live returns success; /health/ready fails clearly when the database is unavailable. |  |
| FND-008 | Built | PostgreSQL connection pool. |  |
| FND-009 | Built | Alembic configured. |  |
| FND-010 | Built | Separate test database configuration. |  |
| FND-011 | Built | CORS allowlist from environment variables. |  |
| FND-012 | Built | API version prefix /api/v1. |  |
| FND-013 | Verified | Frontend layout: src/{app,api,auth,components,features,layouts,routes,styles,test}, public/, package.json, vite.config.ts, tsconfig.json. |  |
| FND-014 | Built | React + TypeScript with strict TypeScript; type check passes. |  |
| FND-015 | Built | Route handling. |  |
| FND-016 | Verified | Shared API client. |  |
| FND-017 | Built | Global error boundary. |  |
| FND-018 | Built | Loading, empty and error components. |  |
| FND-019 | Built | Accessible form controls. |  |
| FND-020 | Verified | Responsive application shell. |  |
| FND-021 | Built | Frontend unit test setup; runner passes. |  |
| FND-022 | Built | Lint and format commands; lint passes. |  |
| FND-023 | Verified | Browser console shows no application errors. |  |
| FND-024 | Verified | Docker Compose for app, database, Redis and local object storage, with health checks and persistent volumes; one documented command starts dependencies; restart preserves database data. |  |
| FND-025 | Verified | .env.example with variable names and safe example values only; .gitignore; no secrets in Git. |  |
| FND-026 | Built | Database migration command; migration runs from an empty database. |  |
| FND-027 | Verified | Development-only seed command for demo accounts; it cannot run in production. |  |
| FND-028 | Built | One automated test command; CI runs the same lint, type-check and test commands. |  |
| FND-029 | Verified | Clean setup documented; backend and frontend start from a clean checkout. |  |

## DB

| ID | State | Requirement | Note |
|---|---|---|---|
| DB-001 | Partly built / needs testing | Migrations create at least: users, roles, permissions, role_permissions, sessions, password_reset_tokens, projects, project_languages, project_memberships, project_audio_rules, project_retention_rules, participants, participant_project_links, consent_records, tasks, task_assignments, task_status_history, task_comments, provider_accounts, call_sessions, call_participants, call_events, provider_webhook_events, recordings, recording_channels, audio_assets, audio_qc_results, transcription_jobs, transcripts, transcript_segments, exports, audit_logs, system_settings. | Tables arrive phase by phase |
| DB-002 | Partly built / needs testing | Every table: primary key, foreign keys, unique constraints, indexes from real query patterns, created/updated timestamps, defined deletion behaviour, constrained status values; soft deletion only where appropriate. | Ongoing every phase |
| DB-003 | Built | Schema changes only through migrations; migration tests apply them to an empty database. |  |
| DB-004 | Built | Workflow state stored in the database, never only in frontend state. |  |
| DB-005 | Built | Sensitive columns documented. |  |
| DB-006 | Partly built / needs testing | No binary audio in PostgreSQL; only object-storage keys and metadata. | Ongoing every phase |

## ROLE

| ID | State | Requirement | Note |
|---|---|---|---|
| ROLE-001 | Verified | Authorization enforced on the backend for every protected API; hidden controls are not security. |  |
| ROLE-002 | Built | Super Admin: full access, system settings and integrations, all users and projects. |  |
| ROLE-003 | Built | Project Admin: assigned projects; create tasks; assign moderators and QC staff; view project reports and recordings. |  |
| ROLE-004 | Verified | Moderator: assigned tasks only; participant details per project policy; start/control assigned calls; record face-to-face; record consent; submit sessions. |  |
| ROLE-005 | Withdrawn | WITHDRAWN (D-062, owner 2026-11-10): no Transcriber role - this is a data collection tool and nobody transcribes by hand. Was: assigned transcription tasks; create, edit, submit transcripts. | D-062 owner 2026-11-10 |
| ROLE-006 | Built | QC Executive: assigned QC tasks only; review recordings (and the AI transcript, read-only, when the project has it on); pass, fail or return with reason codes and comments. |  |
| ROLE-007 | Built | Client Viewer: read-only, explicitly shared project results only; no internal notes or restricted participant data. |  |
| ROLE-008 | Verified | Permission matrix documented and used as the source of the every-role-against-every-API test. |  |
| ROLE-009 | Built | Role and permission constants defined centrally, including users.manage, projects.manage, tasks.assign, calls.start, recordings.view, recordings.download, audio_qc.review, asr.manage, exports.create, audit.view. |  |
| ROLE-010 | Built | A backend permission dependency is applied to every protected API, with project membership checks. |  |
| ROLE-011 | Verified | Frontend route and navigation filtering for usability only; changing the route manually does not bypass permissions. |  |
| ROLE-012 | Verified | Direct API tests per role: moderator cannot call user management; QC Executive cannot download an unassigned recording; QC Executive reaches assigned items only; Client Viewer is read-only. |  |

## AUTH

| ID | State | Requirement | Note |
|---|---|---|---|
| AUTH-001 | Verified | Login with correct credentials succeeds (POST /api/v1/auth/login). |  |
| AUTH-002 | Verified | Wrong credentials fail. |  |
| AUTH-003 | Verified | Logout revokes the session on the server (POST /api/v1/auth/logout). |  |
| AUTH-004 | Verified | Password reset with expiring single-use tokens (POST /api/v1/auth/password/forgot, /password/reset). |  |
| AUTH-005 | Built | Session expiry; an expired session requires login. |  |
| AUTH-006 | Built | Passwords hashed with a modern adaptive algorithm. |  |
| AUTH-007 | Built | Account active/disabled state; disabled users cannot log in. |  |
| AUTH-008 | Built | Optional multi-factor authentication, added only after the base flow is secure. | D-106: required for Super Admin and Project Admin (owner decision); optional for other roles |
| AUTH-009 | Built | Failed login throttling blocks repeated failures. |  |
| AUTH-010 | Built | Session and device management, including revocation. |  |
| AUTH-011 | Verified | Role and project access enforced; a moderator cannot open admin APIs by changing a URL or calling the API outside the UI. |  |
| AUTH-012 | Built | User model with normalized unique email/username. |  |
| AUTH-013 | Built | Secure HTTP-only SameSite cookies (or a documented secure token strategy); no long-lived secrets in browser local storage. |  |
| AUTH-014 | Built | Audit events for login failures, password changes and account disablement. |  |
| AUTH-015 | Built | GET /api/v1/auth/me returns the current user; no API ever returns a password or hash. |  |
| AUTH-016 | Verified | Frontend: login, forgot password, reset password pages, session-expired message, protected route wrapper. |  |

## USER

| ID | State | Requirement | Note |
|---|---|---|---|
| USER-001 | Verified | Create, edit, deactivate and reactivate users. |  |
| USER-002 | Built | Assign roles. |  |
| USER-003 | Built | Assign project membership. |  |
| USER-004 | Verified | User list with search, filter and pagination. |  |
| USER-005 | Built | CSV import with validation preview. |  |
| USER-006 | Built | CSV export with permission checks (authorized admins only). |  |
| USER-007 | Built | Every role and membership change audited with who made it. |  |
| USER-008 | Built | A deactivated user loses access immediately or at the next enforced session check. |  |
| USER-009 | Verified | One user per role created; each sees only permitted pages and data. |  |

## PROJ

| ID | State | Requirement | Note |
|---|---|---|---|
| PROJ-001 | Built | Project create/edit; unique project code and name. |  |
| PROJ-002 | Built | Languages and dialects. |  |
| PROJ-003 | Built | Allowed recording modes. |  |
| PROJ-004 | Built | Daily recording targets. |  |
| PROJ-005 | Built | Audio specification fields. |  |
| PROJ-006 | Withdrawn | WITHDRAWN (D-062): transcription guidelines with version (only manual transcribers used them). | D-062 owner 2026-11-10 |
| PROJ-007 | Built | QC rules per project. |  |
| PROJ-008 | Built | Retention policy. |  |
| PROJ-009 | Built | Lifecycle status: draft, active, paused, completed, archived. |  |
| PROJ-010 | Built | Archived projects receive no new work unless an authorized admin reopens them. |  |
| PROJ-011 | Partly built / needs testing | Project settings appear in task creation and reports. | Task creation uses project modes; reports in Phase 9 |
| PROJ-012 | Built | Project isolation enforced. |  |
| PROJ-013 | Verified | Frontend: project list, create/edit, detail tabs overview, team, audio rules, language, retention. |  |

## PART

| ID | State | Requirement | Note |
|---|---|---|---|
| PART-001 | Verified | Participant A and B records attached to a task. |  |
| PART-002 | Verified | Unique participant ID from a participant ID generator. |  |
| PART-003 | Built | Name or approved display label. |  |
| PART-004 | Verified | Phone number for telephony tasks, normalized to one format. |  |
| PART-005 | Built | Language and dialect. |  |
| PART-006 | Verified | Consent stored separately from the profile: status, method, time, staff member, policy/version; consent audit history. |  |
| PART-007 | Built | Duplicate participant detection. |  |
| PART-008 | Verified | Restricted personal data; phone numbers visible only with permission, masked otherwise. |  |
| PART-009 | Verified | Retention and deletion support. |  |
| PART-010 | Verified | Only necessary participant details stored. |  |
| PART-011 | Built | Unauthorized users cannot export participant contact details. |  |
| PART-012 | Built | Participant correction workflow. |  |
| PART-013 | Built | Participant personal page (owner 2026-11-10): staff create a private, expiring, replaceable link for one participant in one project; without an account the participant sees only their own participant code, their own sessions (date, type, length, state) and accepted recording time - no names, phone numbers, other speaker or audio; an invalid, expired, replaced or revoked link answers like one that never existed; the link's secret is stored hashed and never travels in an address. |  |
| PART-014 | Built | Consent form (owner 2026-11-10): each project has a consent form text with a version; the participant reads it on their personal page and answers agree / do not agree, and may withdraw later; every answer is stored with time and version as the participant's own (no staff member), audited, and shown to staff in the consent history. |  |
| PART-015 | Built | Consent record with every recording (owner 2026-11-10): each recording has a printable consent record - both participants by code, the consent recorded for the session, each participant's own answers with the form text they answered, version and time, and the checksums of the audio files it belongs to - and it downloads together with the recording, under the same download right. |  |
| PART-016 | Built | Participants section (owner 2026-11-10): a menu entry of its own for people who manage participants, listing a project's participants with contact and consent state; add one or add many from a CSV file (rows are checked first, only rows without a problem are added); on a selection: assign to another project, send the consent form by email, remove (with a reason). Every bulk action reports each participant's result and applies the same permissions, limits and audit entries as the single action. |  |
| PART-017 | Built | Consent review (owner 2026-11-10): a participant's own 'agree' answer waits for review; a person who manages participants approves it or rejects it with a note; the participant sees the note on their page and can answer again; the form can be sent again at any time. Reviews are audited. |  |

## TASK

| ID | State | Requirement | Note |
|---|---|---|---|
| TASK-001 | Verified | Create task with project, mode, Participant A, Participant B, target/due date, priority; assign moderator. |  |
| TASK-002 | Verified | Lifecycle DRAFT -> ASSIGNED -> IN_PROGRESS -> RECORDED -> AUDIO_QC -> APPROVED (D-062: the transcription and transcript QC states were removed). |  |
| TASK-003 | Verified | Exception states REJECTED, RETURNED, CANCELLED, ON_HOLD with reason codes. |  |
| TASK-004 | Verified | Invalid or arbitrary state jumps rejected at API level (and in the UI). |  |
| TASK-005 | Verified | Only the assigned moderator sees and starts the task. |  |
| TASK-006 | Built | Reassignment requires a reason and creates history. |  |
| TASK-007 | Verified | Task comments and history timeline. |  |
| TASK-008 | Verified | Every state change records user, time and reason. |  |
| TASK-009 | Built | Allowed statuses and transitions defined in one backend service. |  |
| TASK-010 | Built | State change and its history row written in one database transaction. |  |
| TASK-011 | Verified | Task list filters and task detail page. |  |
| TASK-012 | Built | Assignment is project-scoped. |  |

## STOR

| ID | State | Requirement | Note |
|---|---|---|---|
| STOR-001 | Verified | Private cloud object storage; bucket never public. |  |
| STOR-002 | Built | Object keys: <project>/face-to-face/YYYY/MM/DD/<task>/original/ and /derived/, <project>/telephony/YYYY/MM/DD/<task>/provider-original/ and /final/, <project>/transcripts/<task>/, <project>/metadata/. |  |
| STOR-003 | Built | Secure upload. |  |
| STOR-004 | Built | Multipart/resumable upload; interrupted upload resumes or restarts safely. |  |
| STOR-005 | Verified | Download authorization with short-lived signed URLs; no predictable public URLs; expired URL stops working. |  |
| STOR-006 | Verified | Upload completion verified; SHA-256 calculated; source and stored checksums compared. |  |
| STOR-007 | Built | Version tracking. |  |
| STOR-008 | Built | Original and derived assets linked; asset metadata saved in the database. |  |
| STOR-009 | Built | Retention rules, backup policy, retention and deletion jobs, deletion workflow with audit log. |  |
| STOR-010 | Built | Storage usage reporting/dashboard. |  |
| STOR-011 | Verified | Unauthorized user cannot download a recording. |  |
| STOR-012 | Built | Storage abstraction interface. |  |
| STOR-013 | Partly built / needs testing | Server-side encryption configured. | Wasabi encryption at rest NOT VERIFIED (docs check pending) |

## FTF

| ID | State | Requirement | Note |
|---|---|---|---|
| FTF-001 | Verified | Browser support check. |  |
| FTF-002 | Verified | Microphone permission requested after a user action; denial gives a clear error. |  |
| FTF-003 | Verified | Microphones enumerated after permission; moderator selects a device. |  |
| FTF-004 | Verified | Live input-level meter. |  |
| FTF-005 | Partly built / needs testing | Short test recording and playback. | Browser plays the delivery file to its end (automated); test playback not yet checked by ear (no speakers on the build machine) |
| FTF-006 | Verified | Project audio rules shown before start. |  |
| FTF-007 | Verified | Start and stop controls; resume; pause only if technically safe. |  |
| FTF-008 | Verified | Recording duration and state displayed. |  |
| FTF-009 | Verified | Interruption/error events captured; recoverable data preserved where safely possible; accurate recovery message after refresh, tab close or network loss; no claim that recording continues after tab closure or device sleep. |  |
| FTF-010 | Verified | Resumable upload with progress and retry. |  |
| FTF-011 | Verified | Browser capture stored as the original asset. |  |
| FTF-012 | Verified | Browser echo cancellation, noise suppression and auto gain requested off; applied settings recorded. |  |
| FTF-013 | Verified | Derived PCM WAV generated and validated. |  |
| FTF-014 | Verified | Session metadata captured. |  |
| FTF-015 | Partly built / needs testing | Tested in supported Chrome and Edge versions; a 60-second sample's original and derived files inspected with an independent tool. | Chrome and Microsoft Edge 156 (Linux, CI) verified with fake microphone; 60-second real sample through ffprobe not done (no ffprobe on the build machine); Edge on Windows not tested |

## AUDIO

| ID | State | Requirement | Note |
|---|---|---|---|
| AUDIO-001 | Blocked | Telephony: one WAV per conversation. | Telephony provider account (B-01) |
| AUDIO-002 | Blocked | Telephony final file: stereo, 16 kHz, 16-bit signed PCM. | Telephony provider account (B-01) |
| AUDIO-003 | Blocked | Left channel = Participant A only; right channel = Participant B only. | Telephony provider account (B-01) |
| AUDIO-004 | Partly built / needs testing | No noise suppression, normalization, compression, EQ or enhancement in either mode. | Face-to-face verified; telephony in Phase 6 |
| AUDIO-005 | Blocked | No lossy compression in the stored final WAV. | Telephony provider account (B-01) |
| AUDIO-006 | Blocked | Provider 'stereo' / 'dual-channel' claims verified on the actual file. | Telephony provider account (B-01) |
| AUDIO-007 | Blocked | No leakage of A into B's channel or B into A's. | Telephony provider account (B-01) |
| AUDIO-008 | Blocked | Moderator introduction excluded from the participant conversation or stored as a separate consent/introduction recording, per the agreed policy. | Telephony provider account (B-01) |
| AUDIO-009 | Blocked | Recording continues after moderator departure. | Telephony provider account (B-01) |
| AUDIO-010 | Blocked | Both participant tracks aligned in time. | Telephony provider account (B-01) |
| AUDIO-011 | Blocked | A mixed mono recording is never copied into left and right; the requirement is marked BLOCKED/unsupported. | Telephony provider account (B-01) |
| AUDIO-012 | Blocked | Separate tracks combined into stereo without altering content; provider originals preserved; every derived-file operation recorded. | Telephony provider account (B-01) |
| AUDIO-013 | Blocked | Actual provider codec and recording specification recorded; no 'uncompressed end-to-end' or native 16 kHz claim for a phone call without provider proof. | Telephony provider account (B-01) |
| AUDIO-014 | Verified | Face-to-face derived target: WAV, mono, 16 000 Hz, 16-bit signed PCM. |  |
| AUDIO-015 | Verified | Original browser capture kept; converted file is a derived asset with conversion details; never described as untouched original. |  |
| AUDIO-016 | Verified | Microphone capture needs HTTPS, user permission and a supported browser; clear microphone test before recording. |  |
| AUDIO-017 | Verified | Every final asset stores: extension and actual container, codec/sample format, sample rate, bit depth, channels, duration, size, peak, clipping count or %, silence %, RMS, hash, source recording ID, processing history. |  |
| AUDIO-018 | Built | QC analysis never modifies source audio. |  |
| AUDIO-019 | Verified | Deterministic, tested processing pipeline. |  |
| AUDIO-020 | Verified | Actual original inspected before conversion; decoded without noise reduction or enhancement; resampled to 16 kHz with a documented high-quality resampler; converted to signed 16-bit; written as WAV; original never overwritten. |  |
| AUDIO-021 | Verified | Conversion to mono only when source channel handling is understood; exact downmix method documented. |  |
| AUDIO-022 | Verified | Processing tool, version, parameters and checksum stored for every derived file. |  |
| AUDIO-023 | Partly built / needs testing | Independent inspection with ffprobe (-v error -show_streams -show_format) or equivalent. | libsndfile check done; ffprobe check runs in CI |
| AUDIO-024 | Blocked | Stereo join of separate tracks used only for genuinely separate, aligned tracks, tested on controlled fixtures first. | Telephony provider account (B-01) |

## TEL

| ID | State | Requirement | Note |
|---|---|---|---|
| TEL-001 | Built | All provider code behind one adapter interface (internal names, e.g. start_call_to_a, add_b_to_conference, join_moderator, start_recording, moderator_leave, end_conference, get_recording, verify_webhook); real calls implemented only from verified official documentation. |  |
| TEL-002 | Built | Create outbound call to Participant A. | Real call to a phone not made yet (TM-TEL-01) |
| TEL-003 | Blocked | Add Participant B to the same conference. | TxContact has no API for this: done in TxContact's own screen (D-101); not verified |
| TEL-004 | Blocked | Join moderator to the conference. | D-101: the moderator is the TxContact agent the call is connected to; not verified |
| TEL-005 | Blocked | Mute/unmute. | TxContact has no API for this: done in TxContact's own screen (D-101); not verified |
| TEL-006 | Blocked | Moderator leaves the conference. | D-103: the moderator stays on the call, muted; leaving is TxContact's screen, not verified |
| TEL-007 | Blocked | End participant conference. | Ended in TxContact's screen; the platform records Close call / Cancel (D-101) |
| TEL-008 | Blocked | Start/stop recording when the provider requires explicit control. | TxContact records the whole call; no explicit control described |
| TEL-009 | Blocked | Receive call and recording webhooks. | TxContact has no webhooks: the platform polls instead (D-101) |
| TEL-010 | Built | Retrieve recording metadata and files. | TxContact's recording login not received; real download not made |
| TEL-011 | Built | Handle provider errors, timeouts and retries. |  |
| TEL-012 | Blocked | Verify webhook signatures; never trust an unsigned webhook. | TxContact has no webhooks: the platform polls instead (D-101) |
| TEL-013 | Blocked | Unique constraint on provider event ID; idempotent processing; duplicate webhooks create no duplicate sessions or files. | TxContact has no webhooks: the platform polls instead (D-101) |
| TEL-014 | Partly built / needs testing | Call sequence implemented in the provider-allowed order: session + conference ID, call A, add B, moderator joins, consent, recording, moderator leaves, bridge continues, close, final event, secure download and validation, audio QC; no invented endpoints. | D-101: A is rung by API, B is added by the moderator in TxContact; the order cannot be enforced |
| TEL-015 | Partly built / needs testing | No participant conversation recorded before required consent for A and B is recorded. | A call is closed and its recording fetched only with both consents; a refusal cancels it. TxContact itself records from the start of the call |
| TEL-016 | Blocked | Participant recording begins at the configured point. | Recording start is TxContact's; not described |
| TEL-017 | Partly built / needs testing | Recording retrieval: recording ID validated against the session; fetched through the authenticated provider API; original saved; type and codec inspected; separate tracks retrieved; A/B mapped; final stereo built and validated; checksums and processing metadata saved; task ready for audio QC only after successful validation. | Fetched through the provider API, original kept, type inspected, checksums and history: built. Separate tracks, A/B mapping, stereo: not possible with TxContact as known (D-101) |
| TEL-018 | Built | Failed calls visible and recoverable; call event history kept. |  |
| TEL-019 | Blocked | Provider acceptance: A and B stay connected after moderator leaves; recording continues; A and B recorded independently; channel mapping correct; recording retrievable through the API. | Needs a real call on the TxContact account |
| TEL-020 | Blocked | 50 simultaneous conferences supported by the purchased account, confirmed in writing, and tested. | TxContact's written answer on concurrency |
| TEL-021 | Partly built / needs testing | At least two providers compared from official documentation and written answers: India outbound, API call creation, conference creation, add participant to active conference, moderator departure without ending, recording continues, separate tracks or verified dual-channel, recording retrieval API, webhooks and signatures, 50 concurrent conferences, call-leg limits, recording format/sample rate, retention and storage, per-minute and fixed costs, contract and compliance (incl. recording consent). | Twelve providers read from official pages plus TxContact; written answers outstanding |
| TEL-022 | Partly built / needs testing | No provider selected on a cheap advertised plan or marketing page. | TxContact came through DesiCrew, chosen by the owner (D-101) |
| TEL-023 | Partly built / needs testing | A provider failing any critical item is not accepted; telephony stays BLOCKED, alternatives presented, unrelated modules continue, no fake integration, no quiet workflow substitution. | D-101: the owner accepted TxContact's limits; Gate 5 proof outstanding |
| TEL-024 | Partly built / needs testing | Full telephony UI not built before the proof of capability passes. | D-101: the owner chose to build the call screen before the proof of capability |
| TEL-025 | Partly built / needs testing | Isolated proof-of-concept with test credentials stored server-side; test call IDs, provider event IDs and files saved as non-sensitive evidence. | Dialer tried on the account without ringing anyone (results in API_NOTES.md); credentials are environment secrets |
| TEL-026 | Blocked | Audio acceptance: A says 'This is participant A.', B says 'This is participant B.'; left alone, right alone, both, leakage, alignment, duration, sample rate, bit depth, PCM codec and moderator presence inspected; a mixed-only result fails. | Needs a real call on the TxContact account |
| TEL-027 | Partly built / needs testing | Domain model stores task ID, provider call ID, conference ID, participant role (A, B, moderator), call state, start/end times, consent status, recording state, provider event IDs, failure code and safe diagnostics. | Task, provider call id and reference, seat, state, times, failure code and safe detail, history: stored. Conference id and per-leg roles do not exist with TxContact |
| TEL-028 | Partly built / needs testing | Server-side call states CREATED, CALLING_A, A_CONNECTED, ADDING_B, B_CONNECTED, MODERATOR_CONNECTED, CONSENT_PENDING, CONSENT_CONFIRMED, RECORDING, MODERATOR_LEFT, PARTICIPANTS_CONTINUING, COMPLETED, FAILED, CANCELLED; invalid transitions fail safely. | States are the ones this flow has (D-101), each change checked on the server; not the specification's list |
| TEL-029 | Built | If A or B refuses consent the session ends or is cancelled per project policy. |  |
| TEL-030 | Blocked | Moderator departure does not end the conference; only an authorized action ends it. | D-103: the moderator stays, muted. Whether leaving ends the call is TxContact's to answer |
| TEL-031 | Blocked | Late and out-of-order webhooks handled correctly. | TxContact has no webhooks: the platform polls instead (D-101) |
| TEL-032 | Blocked | Webhooks acknowledged quickly; heavy work processed asynchronously; raw event metadata stored safely. | TxContact has no webhooks: the platform polls instead (D-101) |
| TEL-033 | Blocked | Transient webhook failures retried; permanent failures go to a dead-letter queue. | TxContact has no webhooks: the platform polls instead (D-101) |
| TEL-034 | Blocked | Admin webhook event viewer. | TxContact has no webhooks: the platform polls instead (D-101) |
| TEL-035 | Built | Recording never downloaded from an arbitrary URL in a webhook without validation. |  |
| TEL-036 | Built | Moderator call UI: assigned task, A/B details, start call, call state, add B, consent checklist for A and B, recording state, leave conference, permission-restricted end session, error/retry display, event timeline. | Add B and mute are in TxContact's screen; walk-through with a real call open (TM-TEL-05) |
| TEL-037 | Built | Every call UI action goes to the backend and shows the actual provider response; no optimistic 'connected' state. |  |
| TEL-038 | Partly built / needs testing | Failure scenarios handled: A no answer, B no answer, B fails to join, moderator drops, participant disconnects, webhook repeats, webhook out of order, retrieval fails and retries, corrupt recording, one channel missing, 50 concurrent sessions. | Tested: no answer and dropped (cancel), provider refuses, retrieval fails and retries, unreadable file, cut-short download, redial, hold, cancel while fetching. Not tested: 50 at once, a missing channel |

## AQC

| ID | State | Requirement | Note |
|---|---|---|---|
| AQC-001 | Built | Project-configured thresholds; initial rule flags silence above 25 %; no hard-coded universal thresholds without evidence. |  |
| AQC-002 | Built | Checks container, codec, sample rate, bit depth, channels, duration, file size. |  |
| AQC-003 | Built | Measures silence ratio, clipping ratio, RMS, peak, dynamic range. |  |
| AQC-004 | Built | SNR only with a validated method; otherwise null with reason. |  |
| AQC-005 | Partly built / needs testing | Channel leakage indicator for stereo telephony. | Correlation indicator built and tested on two-channel files; telephony stereo files need B-01 |
| AQC-006 | Built | Missing, corrupt or undecodable audio detected (decode errors recorded). |  |
| AQC-007 | Built | Duplicate audio detection (hash and content). |  |
| AQC-008 | Built | Outcome PASS, FAIL or NEEDS_REVIEW with reason code, comment, timestamp and reviewer ID. |  |
| AQC-009 | Built | Read-only analysis service; never modifies the source. |  |
| AQC-010 | Partly built / needs testing | Fixture tests: valid mono, valid stereo, wrong sample rate, wrong bit depth, wrong channel count, silence, clipping, corrupt, swapped channels, identical left/right mixed tracks, missing track. | All fixtures pass except swapped channels, which needs a telephony reference recording (B-01) |

## ASR

| ID | State | Requirement | Note |
|---|---|---|---|
| ASR-001 | Not built | Provider-neutral ASR interface: submit job, get status, retrieve result, cancel if supported. |  |
| ASR-002 | Not built | AI transcription provider: Deepgram (owner decision 2026-11-09, replaces the spec's initial candidates Whisper Large-v3 / AI4Bharat); its capabilities, models, language coverage and prices used only after official-documentation check and evaluation; other providers only after evaluation. |  |
| ASR-003 | Not built | Audio queued for transcription after it passes audio QC. |  |
| ASR-004 | Not built | Language and dialect selected per job. |  |
| ASR-005 | Not built | Stored per job: provider/model name, exact version, language, settings, source asset ID, status, start/end times, raw response, normalized transcript, error details. |  |
| ASR-006 | Not built | Timestamps, speaker labels and confidence stored only when the model returns them; otherwise null. |  |
| ASR-007 | Not built | Bounded retries; permanent failure visible to admin. |  |
| ASR-008 | Not built | Worker fetches audio through an authorized service; the AI transcript is stored beside the recording and never holds up the task (D-062). |  |
| ASR-010 | Not built | AI transcription is optional: an on/off setting per project (default off); when off, no ASR job is created or sent; when on but the Deepgram key is missing, the UI and API show Not configured; the recording and QC workflow is the same either way (D-062). |  |
| ASR-009 | Not built | Labelled reference set per launch language/dialect; WER/CER, speaker-label accuracy if supported, timestamp error, processing time, cost per audio hour; dataset size and method recorded; no claims from tiny samples. |  |

## TRN

| ID | State | Requirement | Note |
|---|---|---|---|
| TRN-001 | Withdrawn | WITHDRAWN (D-062): Assigned task queue; a transcriber cannot open or edit another person's task. | D-062 owner 2026-11-10 |
| TRN-002 | Withdrawn | WITHDRAWN (D-062): Audio player with playback speed, seek and segment navigation. | D-062 owner 2026-11-10 |
| TRN-003 | Withdrawn | WITHDRAWN (D-062): Transcript editor with speaker labels and timestamp editing. | D-062 owner 2026-11-10 |
| TRN-004 | Withdrawn | WITHDRAWN (D-062): Draft status, save draft and autosave endpoints; visible save status; draft survives refresh. | D-062 owner 2026-11-10 |
| TRN-005 | Withdrawn | WITHDRAWN (D-062): Submit endpoint; submission locks the submitted version and moves the task to transcript QC. | D-062 owner 2026-11-10 |
| TRN-006 | Withdrawn | WITHDRAWN (D-062): Revision history endpoint; prior versions available. | D-062 owner 2026-11-10 |
| TRN-007 | Withdrawn | WITHDRAWN (D-062): Keyboard shortcuts. | D-062 owner 2026-11-10 |
| TRN-008 | Withdrawn | WITHDRAWN (D-062): Project transcription rules; verbatim transcription; language-specific scripts. | D-062 owner 2026-11-10 |
| TRN-009 | Withdrawn | WITHDRAWN (D-062): A returned task shows the transcriber the reason and revision request. | D-062 owner 2026-11-10 |
| TRN-010 | Withdrawn | WITHDRAWN (D-062): Concurrent edits detected. | D-062 owner 2026-11-10 |
| TRN-011 | Withdrawn | WITHDRAWN (D-062): Autosave failure visible to the user. | D-062 owner 2026-11-10 |
| TRN-012 | Withdrawn | WITHDRAWN (D-062): Assignment endpoint. | D-062 owner 2026-11-10 |

## TQC

| ID | State | Requirement | Note |
|---|---|---|---|
| TQC-001 | Withdrawn | WITHDRAWN (D-062): Audio and transcript side by side; segment playback. | D-062 owner 2026-11-10 |
| TQC-002 | Withdrawn | WITHDRAWN (D-062): Edit or annotate if permission allows. | D-062 owner 2026-11-10 |
| TQC-003 | Withdrawn | WITHDRAWN (D-062): Approve, reject, return for correction; a revised transcript creates a new version. | D-062 owner 2026-11-10 |
| TQC-004 | Withdrawn | WITHDRAWN (D-062): Error categories, reviewer comments, QC history. | D-062 owner 2026-11-10 |
| TQC-005 | Withdrawn | WITHDRAWN (D-062): Final lock after approval; reopening needs permission, reason and audit entry. | D-062 owner 2026-11-10 |
| TQC-006 | Withdrawn | WITHDRAWN (D-062): One task completed end to end (recording, audio QC, ASR, human correction, transcript QC, approval) with evidence for each transition. | D-062 owner 2026-11-10 |

## EXP

| ID | State | Requirement | Note |
|---|---|---|---|
| EXP-001 | Partly built / needs testing | Export: final WAV, original recordings where permitted, face-to-face recordings, transcript text, timestamped segments, speaker labels, participant IDs, project/task metadata, language/dialect, consent metadata subject to permission, audio QC, processing/model provenance. | Everything listed except transcript text, segments and speaker labels: this version makes no transcripts (ASR: B-06, B-07) |
| EXP-002 | Built | Formats CSV, TSV, JSON, WAV, ZIP with manifest and checksums. |  |
| EXP-003 | Built | JSON matches its schema. |  |
| EXP-004 | Built | Phone numbers excluded by default; unauthorized data excluded; unauthorized roles cannot export restricted personal data. |  |
| EXP-005 | Built | Counts match selected records; ZIP contents match manifest; hashes match. |  |
| EXP-006 | Built | Face-to-face and telephony audio and transcripts in separate folders. |  |
| EXP-007 | Partly built / needs testing | CSV/TSV open correctly in spreadsheet software. | Tables carry the UTF-8 mark and guard formulas (backend/tests/test_exports_zip.py); opening them in spreadsheet software (TM-EXP-01) is to do by a person |
| EXP-008 | Built | Export filters validated and export permissions checked. |  |
| EXP-009 | Built | Large exports generated asynchronously; export status stored. |  |
| EXP-010 | Built | Short-lived download link; export creation and download audited; temporary bundles expire. |  |

## DASH

| ID | State | Requirement | Note |
|---|---|---|---|
| DASH-001 | Partly built / needs testing | Metrics: total tasks, tasks by status, recording hours by mode, daily/monthly target progress, moderator output, QC pass/fail, pending queues, failed calls, failed uploads, storage usage, provider usage and cost estimates. | Everything listed except cost estimates, which need provider rates (DASH-005, B-01); phone calls added (D-108) |
| DASH-002 | Built | Filters: project, date range, language, dialect, mode, staff, status. |  |
| DASH-003 | Built | Every metric reconciles with an independent SQL query, including date boundaries and timezone handling. |  |
| DASH-004 | Built | Role and project visibility enforced. |  |
| DASH-005 | Blocked | Provider charges labelled as estimates with rate source and date. | Telephony provider (B-01): no charges yet |
| DASH-006 | Built | Empty datasets and large date ranges handled. |  |

## SEC

| ID | State | Requirement | Note |
|---|---|---|---|
| SEC-001 | Partly built / needs testing | Audit log for sensitive actions; audit log integrity reviewed. | Integrity review (TM-SEC-06) in Phase 10 |
| SEC-002 | Blocked | TLS everywhere. | Hosting and domain (B-04, B-09) |
| SEC-003 | Partly built / needs testing | Encryption at rest, including backups. | Wasabi encryption at rest NOT VERIFIED; backups unencrypted (B-14) |
| SEC-004 | Built | Secret manager; no secrets in frontend code or Git; repository secret scan. |  |
| SEC-005 | Built | Rate limits. |  |
| SEC-006 | Built | Input validation. |  |
| SEC-007 | Built | Protection against common web vulnerabilities, including CSRF where cookie auth is used. |  |
| SEC-008 | Built | Backup and restore; restore tested into a test environment. |  |
| SEC-009 | Built | Data retention and deletion enforced. |  |
| SEC-010 | Built | Consent record access controls. |  |
| SEC-011 | Built | Role escalation attempts and unauthorized recording downloads fail. |  |
| SEC-012 | Blocked | Webhook signature failures rejected. | Telephony provider (B-01) |
| SEC-013 | Built | Output encoding and secure HTTP headers. |  |
| SEC-014 | Blocked | Least-privilege cloud roles. | Hosting (B-04) |
| SEC-015 | Built | Dependency vulnerability scan. | Moderate dev-only advisory recorded |

## PWA

| ID | State | Requirement | Note |
|---|---|---|---|
| PWA-001 | Not built | manifest.webmanifest with app name, short name, standalone display, theme/background colours, icons in required sizes. |  |
| PWA-002 | Not built | Install prompt where supported; standalone launch. |  |
| PWA-003 | Not built | Responsive layouts. |  |
| PWA-004 | Not built | Service worker caches only safe static assets; no private audio or participant data in shared browser storage. |  |
| PWA-005 | Not built | Update detection with reload prompt; a published update reaches the user. |  |
| PWA-006 | Not built | Offline message for unsupported actions. |  |
| PWA-007 | Not built | Logout clears sensitive local session state. |  |
| PWA-008 | Not built | Installation tested on desktop Chrome and a supported mobile browser. |  |
| PWA-009 | Not built | Install guidance for supported browsers. |  |

## OPS

| ID | State | Requirement | Note |
|---|---|---|---|
| OPS-001 | Blocked | Separate local, test/staging and production environments. | Hosting (B-04) |
| OPS-002 | Blocked | Deployed components: frontend, backend, PostgreSQL, Redis, workers, private object storage, reverse proxy/ingress, monitoring and logs; infrastructure configuration in the repository. | Hosting (B-04) |
| OPS-003 | Blocked | Secrets created in a cloud secret manager. | Hosting (B-04) |
| OPS-004 | Partly built / needs testing | Database backups and object storage lifecycle configured. | Backup commands and restore tested in CI; production schedule and lifecycle wait for B-04, B-14 |
| OPS-005 | Blocked | Health checks, TLS, domain and DNS configured. | Hosting and domain (B-04, B-09) |
| OPS-006 | Partly built / needs testing | Monitoring (logs, metrics, error tracking), alerting and log retention configured; alerts work. | Self-check, status page and alert emails built (D-109); error tracking and metrics need a service account (B-04); alert address to be set on the live copy; TM-SEC-04, TM-OPS-02 to do |
| OPS-007 | Blocked | Database migrations run as a controlled release step. | Hosting (B-04) |
| OPS-008 | Partly built / needs testing | Rollback procedure, disaster recovery runbook and incident runbook exist. | Runbooks written (D-109); nobody has rehearsed them (TM-OPS-04) |
| OPS-009 | Blocked | Clean deployment reproduced from docs/DEPLOYMENT.md; backup restore tested. | Hosting (B-04) |

## LOAD

| ID | State | Requirement | Note |
|---|---|---|---|
| LOAD-001 | Blocked | Load test: 50 simultaneous call setups, 50 active conferences, moderator departure from all 50. | Telephony provider (B-01) |
| LOAD-002 | Blocked | 100 participant legs when moderators join by web/VoIP; leg count recalculated if moderators use phone legs. | Telephony provider (B-01) |
| LOAD-003 | Partly built / needs testing | Load test: concurrent recording downloads and uploads, ASR backlog, QC activity, dashboard queries, webhook bursts. | Development-server run done (Option G); production run and telephony load in Phase 10 (CAP-004) |
| LOAD-004 | Blocked | 250 recording hours/day (125 per mode) processed. | Telephony provider and production hosting (B-01, B-04) |
| LOAD-005 | Partly built / needs testing | Report: date, environment, concurrent users/calls, API latency, call setup success, provider concurrency, worker queue delay, upload throughput, storage growth, ASR throughput, database CPU/connections, memory, network, error rates, recording success and integrity, bottlenecks and fixes. | Development-server run done (Option G); production run and telephony load in Phase 10 (CAP-004) |

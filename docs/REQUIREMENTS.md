# Requirements

Sources, both binding:
- **S** = "Conversation Collection Platform - Claude Code execution plan and verification rules",
  version 1.0, supplied by the owner in chat on 2026-11-09 (section numbers, e.g. `S6 M7`).
- **R** = "Claude Code: Step-by-Step Implementation Runbook", supplied 2026-11-09, copied verbatim to
  `docs/RUNBOOK_SOURCE.md` (part and item numbers, e.g. `R G2.11`).

Where the two say the same thing, one requirement cites both. Where they differ, the difference is
recorded in DECISIONS.md and the stricter reading is used.

## 1. Product in one paragraph

One cloud-hosted, responsive web application, installable as a PWA, for collecting two-person
conversation recordings in two modes. Telephony: a moderator starts a provider conference with
Participants A and B, gets consent, leaves; A and B keep talking; the output is one stereo 16 kHz
16-bit PCM WAV with A left and B right, plus the provider's original files. Face-to-face: a computer
browser records two people near one microphone; the browser original is kept and a mono 16 kHz
16-bit PCM WAV is derived. Recordings go through audio QC and export (AI transcription is an optional per-project add-on;
nobody transcribes by hand, D-062), under five server-enforced roles, with dashboards, audit and privacy controls.
Targets: 50 staff, 50 concurrent conferences, 250 recording hours/day split 125/125.

## 2. Fixed constraints

- No native Android or iOS app; participants install nothing; no GSM gateway (PROD-003).
- No noise suppression, normalization, compression, EQ or enhancement on delivered audio (AUDIO-004).
- A mixed recording is never passed off as separate speakers (AUDIO-011).
- No provider, model, price or format claim without official documentation or a working test (GEN-005).
- Capacity is proven only by load test plus written provider confirmation (CAP-004).

## 3. Out of scope

Native mobile or desktop apps, GSM hardware, audio clean-up of delivered files, choosing a telephony
provider without written evidence.

## 4. Differences between the two sources (resolved in DECISIONS.md)

| Topic | Spec | Runbook | Used |
|---|---|---|---|
| Status words | "Not started", "Verified" ... | `NOT STARTED`, `VERIFIED` ... | Runbook words (D-014) |
| Membership table | `user_project_memberships` | `project_memberships` | `project_memberships` (D-015) |
| Asset table | `audio_assets` | `recording_assets` (I1) and `audio_assets` (N) | one table `audio_assets` (D-015) |
| Phase 0 documents | six named + "seven" | thirteen named + two folders | runbook list (D-013) |
| Face-to-face recovery | no private audio in browser storage by default | preserve local recoverable data where safely possible | chunks uploaded during recording, nothing in browser storage (D-005) |
| Lossless conversion | "documented lossless PCM conversion" | "documented high-quality resampler" | resample is documented and labelled derived; client asked (B-03) |

## 5. ID scheme

`<PREFIX>-<NNN>`. The runbook's suggested prefixes are used where it names one (AUTH, USER, PROJ,
PART, TASK, TEL, FTF, STOR, AQC, ASR, TRN, TQC, EXP, DASH, SEC, PWA, OPS); extra prefixes cover rules
it does not prefix (GEN, PROC, PROD, CAP, ARCH, FND, DB, ROLE, AUDIO, LOAD). Every requirement names
at least one test in TEST_PLAN.md (TA- automated, TM- manual). Planned database/API/UI locations and
status: REQUIREMENT_TRACEABILITY.md.

## 6. Requirements

### GEN - Contract and work rules

Phase: All | Requirements: 14

| ID | Requirement | Source |
|---|---|---|
| GEN-001 | Specification and runbook are the binding contract; the whole runbook is read before code changes; no module skipped, silently removed or silently changed. | S1, S12.6-7; R A1.1, R S |
| GEN-002 | No fake data, mocked success, dummy buttons, placeholder pages, stub methods, TODO, FIXME or NotImplemented in production paths or in any feature marked complete; mocks only in isolated tests. | S1, S12.1-5; R A1.8-10 |
| GEN-003 | A module is complete only when code exists, the app runs, the feature works, automated tests pass, the manual checklist passes and evidence is in BUILD_STATUS.md. | S1 |
| GEN-004 | A blocked requirement is marked BLOCKED with evidence; provider-independent parts are built behind an adapter or marked boundary; an unconfigured external service shows a truthful Not configured state; nothing pretends to work. | S1; R A1.11, R H4, R S |
| GEN-005 | No invented telephony endpoints, provider features, prices, compliance permissions, audio formats or model capabilities; official documentation URL, access date, feature and test evidence saved in docs/integrations/. | S1, S12.8; R A1.12-13 |
| GEN-006 | Evidence per module in docs/evidence/ (files, migrations, API routes, UI routes, tests and results, manual steps and results, screenshots where useful, defects, remaining work, commit hash); no real personal data or secrets in evidence. | S14 |
| GEN-007 | A test not run is reported NOT RUN with the reason and its requirement is not marked verified; unfinished work is INCOMPLETE; undocumented provider claims are NOT VERIFIED. | S17; R A1.14 |
| GEN-008 | No failing tests reported as success; no swallowed exceptions - errors are logged and surfaced. | S12.14-15 |
| GEN-009 | Existing working code preserved (no delete or rewrite without reason and approval); one small task at a time; when context or time runs out, save state, update the tracker and stop at a clean checkpoint. | S12.16-17, S12.20; R A1.3, A1.5, A1.15 |
| GEN-010 | After each task: format, lint, type-check, test, inspect the diff, update the tracker. | R A1.6 |
| GEN-011 | Requirement IDs appear in the tracker, in tests, and in code comments where useful. | R A1.4 |
| GEN-012 | Status vocabulary only: NOT STARTED, IN PROGRESS, BLOCKED, IMPLEMENTED — TESTS FAILING, IMPLEMENTED — AUTOMATED TESTS PASS, VERIFIED, ACCEPTED; VERIFIED needs automated and manual verification; ACCEPTED needs gate approval. | S13; R A3 |
| GEN-013 | No 'fully done' style claims unless the relevant acceptance gate has passed. | R A2 |
| GEN-014 | All applicable automated test layers exist: unit, API, database, integration (isolated test doubles), contract (provider mapping against documented schemas), audio fixtures, frontend, end-to-end, security, load; screenshots never replace integration tests. | R P |

### PROC - Build order, gates, tracking and reporting

Phase: All | Requirements: 9

| ID | Requirement | Source |
|---|---|---|
| PROC-001 | Phases run in order; the next phase starts only after the current gate passes; no gate skipped. | S11; R A1.7, R S |
| PROC-002 | Phase 0 documentation: REQUIREMENTS, REQUIREMENT_TRACEABILITY, ARCHITECTURE, DATABASE, API_CONTRACT, SECURITY, AUDIO_SPECIFICATION, TELEPHONY_PROVIDER_EVALUATION, TEST_PLAN, BUILD_STATUS, DECISIONS, TECH_STACK, DEPLOYMENT, integrations/, evidence/. | S11 Ph0; R C0.2 |
| PROC-003 | Phase 0 inspection commands (pwd, ls -la, find, git status --short, git log -5 --oneline) run and recorded; manifests, dependency files, Docker files, env examples, migrations, tests, CI and deployment config inspected; secret values never printed. | S16.1; R C0.1 |
| PROC-004 | Traceability rows hold ID, requirement, phase, database, API, UI, test, status, evidence. | S16.3; R C0.3 |
| PROC-005 | BUILD_STATUS.md has one row per module and one per requirement (Requirement ID, Description, Phase, Backend, Database, Frontend, Automated test, Manual test, Evidence path, Status, Blocker); every checkbox links to real evidence or stays unchecked; updated every session. | S13; R Q |
| PROC-006 | End of every session: git status --short, git diff --check, relevant tests, tracker update, remaining work recorded; commit only if the owner's workflow permits. | R Q |
| PROC-007 | Report after every session/phase in the required format (runbook A2 fields, spec 17 items), with exact commands and files. | S17; R A2, R S.10 |
| PROC-008 | Ask only for truly blocking decisions or credentials; owner approval before major architectural changes or deleting code; stop after Phase 0 and request approval. | S11, S16.5; R C0.4, R S |
| PROC-009 | Project called complete or production-ready only when the definition of done (spec 15) and every final release checklist item (runbook R) are met. | S15, S12.19; R R |

### PROD - Product scope

Phase: 1, 10 | Requirements: 4

| ID | Requirement | Source |
|---|---|---|
| PROD-001 | One cloud-hosted, responsive web application used through a browser. | S2; R B1 |
| PROD-002 | Installable as a PWA from the browser's install option. | S2; R B1 |
| PROD-003 | No native Android or iOS app; participants install nothing; no physical GSM gateway. | S2; R B1 |
| PROD-004 | Two recording modes - telephony and face-to-face - with assets in separate folders/prefixes. | S2; R B1 |

### CAP - Capacity and configuration

Phase: 2, 10 | Requirements: 5

| ID | Requirement | Source |
|---|---|---|
| CAP-001 | Capacity settings (50 staff, 50 concurrent conferences, 2 participants, 250 h/day, 125 h/day each mode, cloud, web + PWA) stored as editable configuration, not source constants. | S3; R B2 |
| CAP-002 | An administrator changes targets without a code deployment. | S3 |
| CAP-003 | Languages configurable per project. | S3 |
| CAP-004 | Capacity is proven only by a load test plus provider-side concurrency confirmation; never from a local or mock test. | S3, S10; R B2, R M4 |
| CAP-005 | Storage sizing: 115.2 MB/h mono, 230.4 MB/h stereo, 43.2 GB/day at target, 1.296 TB/30 days, about 15.77 TB/year, excluding originals, backups, replicas, metadata and derived copies; retention confirmed before final sizing. | S9; R O |

### ARCH - Architecture and technology

Phase: 0, 1 | Requirements: 5

| ID | Requirement | Source |
|---|---|---|
| ARCH-001 | Modular monolith first; no unnecessary microservices. | S7 |
| ARCH-002 | Stack: React + TypeScript, FastAPI, PostgreSQL, Alembic, Celery + Redis, FFmpeg + a tested Python audio library, private S3-compatible storage, Docker, Nginx or managed ingress, web manifest + service worker; Pytest, Vitest/React Testing Library, Playwright; unless the repository already has a functioning equivalent. | S7; R B4 |
| ARCH-003 | Stable versions pinned and recorded in docs/TECH_STACK.md. | S7; R B4 |
| ARCH-004 | Cloud region chosen for data residency, latency and client requirements; recorded as a decision. | S7 |
| ARCH-005 | Repository inspected before choosing or changing frameworks. | R A1.2 |

### FND - Phase 1 foundation

Phase: 1 | Requirements: 29

| ID | Requirement | Source |
|---|---|---|
| FND-001 | Backend layout: app/main.py, core/{config,logging,security,errors}.py, api/router.py, db/{base,session}.py, db/migrations/, modules/, tests/, pyproject.toml, Dockerfile. | R D1 |
| FND-002 | FastAPI application factory. | R D1.1 |
| FND-003 | Configuration from environment variables; required variables validated at startup; invalid configuration prevents unsafe startup. | S11 Ph1; R D1.2-3 |
| FND-004 | Structured JSON logging with request IDs and no secrets. | S11 Ph1; R D1.4 |
| FND-005 | Request ID middleware. | R D1.5 |
| FND-006 | Global exception handlers. | R D1.6 |
| FND-007 | /health/live returns success; /health/ready fails clearly when the database is unavailable. | S11 Ph1; R D1.7 |
| FND-008 | PostgreSQL connection pool. | R D1.8 |
| FND-009 | Alembic configured. | R D1.9 |
| FND-010 | Separate test database configuration. | R D1.10 |
| FND-011 | CORS allowlist from environment variables. | R D1.11 |
| FND-012 | API version prefix /api/v1. | R D1.12 |
| FND-013 | Frontend layout: src/{app,api,auth,components,features,layouts,routes,styles,test}, public/, package.json, vite.config.ts, tsconfig.json. | R D2 |
| FND-014 | React + TypeScript with strict TypeScript; type check passes. | R D2.1-2 |
| FND-015 | Route handling. | R D2.3 |
| FND-016 | Shared API client. | R D2.4 |
| FND-017 | Global error boundary. | R D2.5 |
| FND-018 | Loading, empty and error components. | R D2.6 |
| FND-019 | Accessible form controls. | R D2.7 |
| FND-020 | Responsive application shell. | R D2.8 |
| FND-021 | Frontend unit test setup; runner passes. | R D2.9 |
| FND-022 | Lint and format commands; lint passes. | R D2.10 |
| FND-023 | Browser console shows no application errors. | R D2 |
| FND-024 | Docker Compose for app, database, Redis and local object storage, with health checks and persistent volumes; one documented command starts dependencies; restart preserves database data. | S11 Ph1; R D3.1-3 |
| FND-025 | .env.example with variable names and safe example values only; .gitignore; no secrets in Git. | S11 Ph1; R D3.4-5 |
| FND-026 | Database migration command; migration runs from an empty database. | S11 Ph1; R D3.6 |
| FND-027 | Development-only seed command for demo accounts; it cannot run in production. | R D3.7-8 |
| FND-028 | One automated test command; CI runs the same lint, type-check and test commands. | S11 Ph1; R D4 |
| FND-029 | Clean setup documented; backend and frontend start from a clean checkout. | S11 Gate1; R D1, R D4 |

### DB - Database model

Phase: 1-9 | Requirements: 6

| ID | Requirement | Source |
|---|---|---|
| DB-001 | Migrations create at least: users, roles, permissions, role_permissions, sessions, password_reset_tokens, projects, project_languages, project_memberships, project_audio_rules, project_retention_rules, participants, participant_project_links, consent_records, tasks, task_assignments, task_status_history, task_comments, provider_accounts, call_sessions, call_participants, call_events, provider_webhook_events, recordings, recording_channels, audio_assets, audio_qc_results, transcription_jobs, transcripts, transcript_segments, exports, audit_logs, system_settings. | S8; R N, R E4, R F1, R I1 |
| DB-002 | Every table: primary key, foreign keys, unique constraints, indexes from real query patterns, created/updated timestamps, defined deletion behaviour, constrained status values; soft deletion only where appropriate. | S8; R N |
| DB-003 | Schema changes only through migrations; migration tests apply them to an empty database. | S8; R N |
| DB-004 | Workflow state stored in the database, never only in frontend state. | S8; R N |
| DB-005 | Sensitive columns documented. | R N |
| DB-006 | No binary audio in PostgreSQL; only object-storage keys and metadata. | R N |

### ROLE - Roles and permissions (RBAC)

Phase: 2 | Requirements: 12

| ID | Requirement | Source |
|---|---|---|
| ROLE-001 | Authorization enforced on the backend for every protected API; hidden controls are not security. | S5, S12.12; R B3, R E2.6 |
| ROLE-002 | Super Admin: full access, system settings and integrations, all users and projects. | S5 |
| ROLE-003 | Project Admin: assigned projects; create tasks; assign moderators and QC staff; view project reports and recordings. | S5 |
| ROLE-004 | Moderator: assigned tasks only; participant details per project policy; start/control assigned calls; record face-to-face; record consent; submit sessions. | S5 |
| ROLE-005 | WITHDRAWN (D-062, owner 2026-11-10): no Transcriber role - this is a data collection tool and nobody transcribes by hand. Was: assigned transcription tasks; create, edit, submit transcripts. | S5 |
| ROLE-006 | QC Executive: assigned QC tasks only; review recordings (and the AI transcript, read-only, when the project has it on); pass, fail or return with reason codes and comments. | S5 |
| ROLE-007 | Client Viewer: read-only, explicitly shared project results only; no internal notes or restricted participant data. | S5 |
| ROLE-008 | Permission matrix documented and used as the source of the every-role-against-every-API test. | S5 |
| ROLE-009 | Role and permission constants defined centrally, including users.manage, projects.manage, tasks.assign, calls.start, recordings.view, recordings.download, audio_qc.review, asr.manage, exports.create, audit.view. | R E2.1 |
| ROLE-010 | A backend permission dependency is applied to every protected API, with project membership checks. | R E2.2-4 |
| ROLE-011 | Frontend route and navigation filtering for usability only; changing the route manually does not bypass permissions. | R E2.5 |
| ROLE-012 | Direct API tests per role: moderator cannot call user management; QC Executive cannot download an unassigned recording; QC Executive reaches assigned items only; Client Viewer is read-only. | R E2 |

### AUTH - Module 1 - Authentication and account security

Phase: 2 | Requirements: 16

| ID | Requirement | Source |
|---|---|---|
| AUTH-001 | Login with correct credentials succeeds (POST /api/v1/auth/login). | S6 M1; R E1.3 |
| AUTH-002 | Wrong credentials fail. | S6 M1; R E1 |
| AUTH-003 | Logout revokes the session on the server (POST /api/v1/auth/logout). | S6 M1; R E1.4 |
| AUTH-004 | Password reset with expiring single-use tokens (POST /api/v1/auth/password/forgot, /password/reset). | S6 M1; R E1.5 |
| AUTH-005 | Session expiry; an expired session requires login. | S6 M1; R E1.8 |
| AUTH-006 | Passwords hashed with a modern adaptive algorithm. | S6 M1; R E1.2 |
| AUTH-007 | Account active/disabled state; disabled users cannot log in. | S6 M1; R E1.7 |
| AUTH-008 | Optional multi-factor authentication, added only after the base flow is secure. | S6 M1; R E1.12 |
| AUTH-009 | Failed login throttling blocks repeated failures. | S6 M1; R E1.6 |
| AUTH-010 | Session and device management, including revocation. | S6 M1; R E1.4 |
| AUTH-011 | Role and project access enforced; a moderator cannot open admin APIs by changing a URL or calling the API outside the UI. | S6 M1 |
| AUTH-012 | User model with normalized unique email/username. | R E1.1 |
| AUTH-013 | Secure HTTP-only SameSite cookies (or a documented secure token strategy); no long-lived secrets in browser local storage. | R E1.9-10 |
| AUTH-014 | Audit events for login failures, password changes and account disablement. | R E1.11 |
| AUTH-015 | GET /api/v1/auth/me returns the current user; no API ever returns a password or hash. | R E1 |
| AUTH-016 | Frontend: login, forgot password, reset password pages, session-expired message, protected route wrapper. | R E1 |

### USER - Module 2 - User management

Phase: 2 | Requirements: 9

| ID | Requirement | Source |
|---|---|---|
| USER-001 | Create, edit, deactivate and reactivate users. | S6 M2; R E3.2, E3.5 |
| USER-002 | Assign roles. | S6 M2; R E3.3 |
| USER-003 | Assign project membership. | S6 M2; R E3.4 |
| USER-004 | User list with search, filter and pagination. | S6 M2; R E3.1 |
| USER-005 | CSV import with validation preview. | S6 M2; R E3.6 |
| USER-006 | CSV export with permission checks (authorized admins only). | S6 M2; R E3.7 |
| USER-007 | Every role and membership change audited with who made it. | S6 M2; R E3.8 |
| USER-008 | A deactivated user loses access immediately or at the next enforced session check. | S6 M2 |
| USER-009 | One user per role created; each sees only permitted pages and data. | S6 M2 |

### PROJ - Module 3 - Project management

Phase: 2 | Requirements: 13

| ID | Requirement | Source |
|---|---|---|
| PROJ-001 | Project create/edit; unique project code and name. | S6 M3; R E4.1-2 |
| PROJ-002 | Languages and dialects. | S6 M3; R E4.3 |
| PROJ-003 | Allowed recording modes. | S6 M3; R E4.4 |
| PROJ-004 | Daily recording targets. | S6 M3; R E4.5 |
| PROJ-005 | Audio specification fields. | S6 M3; R E4.6 |
| PROJ-006 | WITHDRAWN (D-062): transcription guidelines with version (only manual transcribers used them). | S6 M3; R E4.7 |
| PROJ-007 | QC rules per project. | S6 M3 |
| PROJ-008 | Retention policy. | S6 M3; R E4.8 |
| PROJ-009 | Lifecycle status: draft, active, paused, completed, archived. | S6 M3; R E4.9 |
| PROJ-010 | Archived projects receive no new work unless an authorized admin reopens them. | S6 M3; R E4.10 |
| PROJ-011 | Project settings appear in task creation and reports. | S6 M3 |
| PROJ-012 | Project isolation enforced. | R E4 |
| PROJ-013 | Frontend: project list, create/edit, detail tabs overview, team, audio rules, language, retention. | R E4 |

### PART - Module 4 - Participant management

Phase: 3 | Requirements: 15

| ID | Requirement | Source |
|---|---|---|
| PART-001 | Participant A and B records attached to a task. | S6 M4 |
| PART-002 | Unique participant ID from a participant ID generator. | S6 M4; R F1.1 |
| PART-003 | Name or approved display label. | S6 M4 |
| PART-004 | Phone number for telephony tasks, normalized to one format. | S6 M4; R F1.3 |
| PART-005 | Language and dialect. | S6 M4 |
| PART-006 | Consent stored separately from the profile: status, method, time, staff member, policy/version; consent audit history. | S6 M4; R F1.6-7 |
| PART-007 | Duplicate participant detection. | S6 M4; R F1.4 |
| PART-008 | Restricted personal data; phone numbers visible only with permission, masked otherwise. | S6 M4; R F1.5 |
| PART-009 | Retention and deletion support. | S6 M4; R F1.9 |
| PART-010 | Only necessary participant details stored. | S6 M4; R F1.2 |
| PART-011 | Unauthorized users cannot export participant contact details. | S6 M4; R F1 |
| PART-012 | Participant correction workflow. | R F1.8 |
| PART-013 | Participant personal page (owner 2026-11-10): staff create a private, expiring, replaceable link for one participant in one project; without an account the participant sees only their own participant code, their own sessions (date, type, length, state) and accepted recording time - no names, phone numbers, other speaker or audio; an invalid, expired, replaced or revoked link answers like one that never existed; the link's secret is stored hashed and never travels in an address. | Owner 2026-11-10 |
| PART-014 | Consent form (owner 2026-11-10): each project has a consent form text with a version; the participant reads it on their personal page and answers agree / do not agree, and may withdraw later; every answer is stored with time and version as the participant's own (no staff member), audited, and shown to staff in the consent history. | Owner 2026-11-10 |
| PART-015 | Consent record with every recording (owner 2026-11-10): each recording has a printable consent record - both participants by code, the consent recorded for the session, each participant's own answers with the form text they answered, version and time, and the checksums of the audio files it belongs to - and it downloads together with the recording, under the same download right. | Owner 2026-11-10 |

### TASK - Module 5 - Task assignment and workflow

Phase: 3 | Requirements: 12

| ID | Requirement | Source |
|---|---|---|
| TASK-001 | Create task with project, mode, Participant A, Participant B, target/due date, priority; assign moderator. | S6 M5; R F2.3-5 |
| TASK-002 | Lifecycle DRAFT -> ASSIGNED -> IN_PROGRESS -> RECORDED -> AUDIO_QC -> APPROVED (D-062: the transcription and transcript QC states were removed). | S6 M5; R F2 |
| TASK-003 | Exception states REJECTED, RETURNED, CANCELLED, ON_HOLD with reason codes. | S6 M5; R F2 |
| TASK-004 | Invalid or arbitrary state jumps rejected at API level (and in the UI). | S6 M5; R F2.11 |
| TASK-005 | Only the assigned moderator sees and starts the task. | S6 M5; R F2 |
| TASK-006 | Reassignment requires a reason and creates history. | S6 M5; R F2.6 |
| TASK-007 | Task comments and history timeline. | S6 M5; R F2.7, F2.10 |
| TASK-008 | Every state change records user, time and reason. | S6 M5 |
| TASK-009 | Allowed statuses and transitions defined in one backend service. | R F2.1-2 |
| TASK-010 | State change and its history row written in one database transaction. | R F2.12 |
| TASK-011 | Task list filters and task detail page. | R F2.8-9 |
| TASK-012 | Assignment is project-scoped. | R F2 |

### STOR - Module 8 - Audio storage and asset management

Phase: 4 | Requirements: 13

| ID | Requirement | Source |
|---|---|---|
| STOR-001 | Private cloud object storage; bucket never public. | S6 M8; R G1.2 |
| STOR-002 | Object keys: <project>/face-to-face/YYYY/MM/DD/<task>/original/ and /derived/, <project>/telephony/YYYY/MM/DD/<task>/provider-original/ and /final/, <project>/transcripts/<task>/, <project>/metadata/. | S6 M8; R G1 |
| STOR-003 | Secure upload. | S6 M8 |
| STOR-004 | Multipart/resumable upload; interrupted upload resumes or restarts safely. | S6 M8; R G1.5 |
| STOR-005 | Download authorization with short-lived signed URLs; no predictable public URLs; expired URL stops working. | S6 M8; R G1.4 |
| STOR-006 | Upload completion verified; SHA-256 calculated; source and stored checksums compared. | S6 M8; R G1.6-8 |
| STOR-007 | Version tracking. | S6 M8 |
| STOR-008 | Original and derived assets linked; asset metadata saved in the database. | S6 M8; R G1.9-10 |
| STOR-009 | Retention rules, backup policy, retention and deletion jobs, deletion workflow with audit log. | S6 M8; R G1.11 |
| STOR-010 | Storage usage reporting/dashboard. | S6 M8; R G1.12 |
| STOR-011 | Unauthorized user cannot download a recording. | S6 M8 |
| STOR-012 | Storage abstraction interface. | R G1.1 |
| STOR-013 | Server-side encryption configured. | R G1.3 |

### FTF - Module 7 - Face-to-face browser recording

Phase: 4 | Requirements: 15

| ID | Requirement | Source |
|---|---|---|
| FTF-001 | Browser support check. | R G2.1 |
| FTF-002 | Microphone permission requested after a user action; denial gives a clear error. | S6 M7; R G2.2 |
| FTF-003 | Microphones enumerated after permission; moderator selects a device. | S6 M7; R G2.3-4 |
| FTF-004 | Live input-level meter. | S6 M7; R G2.5 |
| FTF-005 | Short test recording and playback. | S6 M7; R G2.6 |
| FTF-006 | Project audio rules shown before start. | R G2.7 |
| FTF-007 | Start and stop controls; resume; pause only if technically safe. | S6 M7; R G2.8 |
| FTF-008 | Recording duration and state displayed. | S6 M7; R G2.9 |
| FTF-009 | Interruption/error events captured; recoverable data preserved where safely possible; accurate recovery message after refresh, tab close or network loss; no claim that recording continues after tab closure or device sleep. | S6 M7; R G2.10-11, G2.14 |
| FTF-010 | Resumable upload with progress and retry. | S6 M7; R G2.12-13 |
| FTF-011 | Browser capture stored as the original asset. | S6 M7; R G2.15, R B1 |
| FTF-012 | Browser echo cancellation, noise suppression and auto gain requested off; applied settings recorded. | S4.2 |
| FTF-013 | Derived PCM WAV generated and validated. | S6 M7 |
| FTF-014 | Session metadata captured. | S6 M7 |
| FTF-015 | Tested in supported Chrome and Edge versions; a 60-second sample's original and derived files inspected with an independent tool. | S6 M7 |

### AUDIO - Audio rules, conversion and validation

Phase: 4-7 | Requirements: 24

| ID | Requirement | Source |
|---|---|---|
| AUDIO-001 | Telephony: one WAV per conversation. | S4.1; R B1 |
| AUDIO-002 | Telephony final file: stereo, 16 kHz, 16-bit signed PCM. | S4.1; R B1.9 |
| AUDIO-003 | Left channel = Participant A only; right channel = Participant B only. | S4.1; R B1.9 |
| AUDIO-004 | No noise suppression, normalization, compression, EQ or enhancement in either mode. | S4.1, S4.2; R G3 |
| AUDIO-005 | No lossy compression in the stored final WAV. | S4.1 |
| AUDIO-006 | Provider 'stereo' / 'dual-channel' claims verified on the actual file. | S4.1 |
| AUDIO-007 | No leakage of A into B's channel or B into A's. | S4.1 |
| AUDIO-008 | Moderator introduction excluded from the participant conversation or stored as a separate consent/introduction recording, per the agreed policy. | S4.1; R H3 |
| AUDIO-009 | Recording continues after moderator departure. | S4.1; R B1.7 |
| AUDIO-010 | Both participant tracks aligned in time. | S4.1 |
| AUDIO-011 | A mixed mono recording is never copied into left and right; the requirement is marked BLOCKED/unsupported. | S4.1, S12.11; R B1 |
| AUDIO-012 | Separate tracks combined into stereo without altering content; provider originals preserved; every derived-file operation recorded. | S4.1; R B1.10 |
| AUDIO-013 | Actual provider codec and recording specification recorded; no 'uncompressed end-to-end' or native 16 kHz claim for a phone call without provider proof. | S4.1; R B1 |
| AUDIO-014 | Face-to-face derived target: WAV, mono, 16 000 Hz, 16-bit signed PCM. | S4.2; R B1, R G3 |
| AUDIO-015 | Original browser capture kept; converted file is a derived asset with conversion details; never described as untouched original. | S4.2; R B1 |
| AUDIO-016 | Microphone capture needs HTTPS, user permission and a supported browser; clear microphone test before recording. | S4.2 |
| AUDIO-017 | Every final asset stores: extension and actual container, codec/sample format, sample rate, bit depth, channels, duration, size, peak, clipping count or %, silence %, RMS, hash, source recording ID, processing history. | S4.3 |
| AUDIO-018 | QC analysis never modifies source audio. | S4.3; R J1 |
| AUDIO-019 | Deterministic, tested processing pipeline. | R G3 |
| AUDIO-020 | Actual original inspected before conversion; decoded without noise reduction or enhancement; resampled to 16 kHz with a documented high-quality resampler; converted to signed 16-bit; written as WAV; original never overwritten. | R G3.1-6, G3.10 |
| AUDIO-021 | Conversion to mono only when source channel handling is understood; exact downmix method documented. | R G3.4 |
| AUDIO-022 | Processing tool, version, parameters and checksum stored for every derived file. | R G3.8-9 |
| AUDIO-023 | Independent inspection with ffprobe (-v error -show_streams -show_format) or equivalent. | R G3.7, R O |
| AUDIO-024 | Stereo join of separate tracks used only for genuinely separate, aligned tracks, tested on controlled fixtures first. | R O |

### TEL - Module 6 - Telephony provider integration

Phase: 5, 6 | Requirements: 38

| ID | Requirement | Source |
|---|---|---|
| TEL-001 | All provider code behind one adapter interface (internal names, e.g. start_call_to_a, add_b_to_conference, join_moderator, start_recording, moderator_leave, end_conference, get_recording, verify_webhook); real calls implemented only from verified official documentation. | S6 M6; R H2.2, R I2 |
| TEL-002 | Create outbound call to Participant A. | S6 M6; R H2.3 |
| TEL-003 | Add Participant B to the same conference. | S6 M6; R H2.4 |
| TEL-004 | Join moderator to the conference. | S6 M6; R H2.5 |
| TEL-005 | Mute/unmute. | S6 M6 |
| TEL-006 | Moderator leaves the conference. | S6 M6; R H2.8 |
| TEL-007 | End participant conference. | S6 M6; R H2.11 |
| TEL-008 | Start/stop recording when the provider requires explicit control. | S6 M6; R H2.7 |
| TEL-009 | Receive call and recording webhooks. | S6 M6; R H2.12 |
| TEL-010 | Retrieve recording metadata and files. | S6 M6; R H2.13 |
| TEL-011 | Handle provider errors, timeouts and retries. | S6 M6 |
| TEL-012 | Verify webhook signatures; never trust an unsigned webhook. | S6 M6; R I4.1, I4.9 |
| TEL-013 | Unique constraint on provider event ID; idempotent processing; duplicate webhooks create no duplicate sessions or files. | S6 M6; R I4.3-4 |
| TEL-014 | Call sequence implemented in the provider-allowed order: session + conference ID, call A, add B, moderator joins, consent, recording, moderator leaves, bridge continues, close, final event, secure download and validation, audio QC; no invented endpoints. | S6 M6 |
| TEL-015 | No participant conversation recorded before required consent for A and B is recorded. | S6 M6; R I3 |
| TEL-016 | Participant recording begins at the configured point. | S6 M6; R H2.7 |
| TEL-017 | Recording retrieval: recording ID validated against the session; fetched through the authenticated provider API; original saved; type and codec inspected; separate tracks retrieved; A/B mapped; final stereo built and validated; checksums and processing metadata saved; task ready for audio QC only after successful validation. | S6 M6; R I6 |
| TEL-018 | Failed calls visible and recoverable; call event history kept. | S6 M6 |
| TEL-019 | Provider acceptance: A and B stay connected after moderator leaves; recording continues; A and B recorded independently; channel mapping correct; recording retrievable through the API. | S6 M6; R H2.9-10 |
| TEL-020 | 50 simultaneous conferences supported by the purchased account, confirmed in writing, and tested. | S6 M6; R H2.20 |
| TEL-021 | At least two providers compared from official documentation and written answers: India outbound, API call creation, conference creation, add participant to active conference, moderator departure without ending, recording continues, separate tracks or verified dual-channel, recording retrieval API, webhooks and signatures, 50 concurrent conferences, call-leg limits, recording format/sample rate, retention and storage, per-minute and fixed costs, contract and compliance (incl. recording consent). | S6 M6; R H1 |
| TEL-022 | No provider selected on a cheap advertised plan or marketing page. | S6 M6; R H1 |
| TEL-023 | A provider failing any critical item is not accepted; telephony stays BLOCKED, alternatives presented, unrelated modules continue, no fake integration, no quiet workflow substitution. | S6 M6; R H4 |
| TEL-024 | Full telephony UI not built before the proof of capability passes. | S11 Ph5; R H |
| TEL-025 | Isolated proof-of-concept with test credentials stored server-side; test call IDs, provider event IDs and files saved as non-sensitive evidence. | S11 Ph5; R H2.1, H2.19 |
| TEL-026 | Audio acceptance: A says 'This is participant A.', B says 'This is participant B.'; left alone, right alone, both, leakage, alignment, duration, sample rate, bit depth, PCM codec and moderator presence inspected; a mixed-only result fails. | R H3 |
| TEL-027 | Domain model stores task ID, provider call ID, conference ID, participant role (A, B, moderator), call state, start/end times, consent status, recording state, provider event IDs, failure code and safe diagnostics. | R I1 |
| TEL-028 | Server-side call states CREATED, CALLING_A, A_CONNECTED, ADDING_B, B_CONNECTED, MODERATOR_CONNECTED, CONSENT_PENDING, CONSENT_CONFIRMED, RECORDING, MODERATOR_LEFT, PARTICIPANTS_CONTINUING, COMPLETED, FAILED, CANCELLED; invalid transitions fail safely. | R I3 |
| TEL-029 | If A or B refuses consent the session ends or is cancelled per project policy. | R I3 |
| TEL-030 | Moderator departure does not end the conference; only an authorized action ends it. | R I3 |
| TEL-031 | Late and out-of-order webhooks handled correctly. | R I3, R I7 |
| TEL-032 | Webhooks acknowledged quickly; heavy work processed asynchronously; raw event metadata stored safely. | R I4.2, I4.5 |
| TEL-033 | Transient webhook failures retried; permanent failures go to a dead-letter queue. | R I4.6-7 |
| TEL-034 | Admin webhook event viewer. | R I4.8 |
| TEL-035 | Recording never downloaded from an arbitrary URL in a webhook without validation. | R I4.10 |
| TEL-036 | Moderator call UI: assigned task, A/B details, start call, call state, add B, consent checklist for A and B, recording state, leave conference, permission-restricted end session, error/retry display, event timeline. | R I5 |
| TEL-037 | Every call UI action goes to the backend and shows the actual provider response; no optimistic 'connected' state. | R I5 |
| TEL-038 | Failure scenarios handled: A no answer, B no answer, B fails to join, moderator drops, participant disconnects, webhook repeats, webhook out of order, retrieval fails and retries, corrupt recording, one channel missing, 50 concurrent sessions. | R I7 |

### AQC - Module 9 - Audio quality control

Phase: 7 | Requirements: 10

| ID | Requirement | Source |
|---|---|---|
| AQC-001 | Project-configured thresholds; initial rule flags silence above 25 %; no hard-coded universal thresholds without evidence. | S6 M9; R J1 |
| AQC-002 | Checks container, codec, sample rate, bit depth, channels, duration, file size. | S6 M9; R J1 |
| AQC-003 | Measures silence ratio, clipping ratio, RMS, peak, dynamic range. | S6 M9; R J1 |
| AQC-004 | SNR only with a validated method; otherwise null with reason. | S6 M9 |
| AQC-005 | Channel leakage indicator for stereo telephony. | S6 M9; R J1 |
| AQC-006 | Missing, corrupt or undecodable audio detected (decode errors recorded). | S6 M9; R J1 |
| AQC-007 | Duplicate audio detection (hash and content). | S6 M9; R J1 |
| AQC-008 | Outcome PASS, FAIL or NEEDS_REVIEW with reason code, comment, timestamp and reviewer ID. | S6 M9; R J1 |
| AQC-009 | Read-only analysis service; never modifies the source. | S6 M9; R J1 |
| AQC-010 | Fixture tests: valid mono, valid stereo, wrong sample rate, wrong bit depth, wrong channel count, silence, clipping, corrupt, swapped channels, identical left/right mixed tracks, missing track. | S6 M9; R J1 |

### ASR - Module 10 - AI transcription

Phase: 7 | Requirements: 10

| ID | Requirement | Source |
|---|---|---|
| ASR-001 | Provider-neutral ASR interface: submit job, get status, retrieve result, cancel if supported. | S6 M10; R J2 |
| ASR-002 | AI transcription provider: Deepgram (owner decision 2026-11-09, replaces the spec's initial candidates Whisper Large-v3 / AI4Bharat); its capabilities, models, language coverage and prices used only after official-documentation check and evaluation; other providers only after evaluation. | S6 M10; owner 2026-11-09 |
| ASR-003 | Audio queued for transcription after it passes audio QC. | S6 M10; R J3.1-3 |
| ASR-004 | Language and dialect selected per job. | S6 M10 |
| ASR-005 | Stored per job: provider/model name, exact version, language, settings, source asset ID, status, start/end times, raw response, normalized transcript, error details. | S6 M10; R J2, J3.6 |
| ASR-006 | Timestamps, speaker labels and confidence stored only when the model returns them; otherwise null. | S6 M10; R J2 |
| ASR-007 | Bounded retries; permanent failure visible to admin. | S6 M10; R J3.8-9 |
| ASR-008 | Worker fetches audio through an authorized service; the AI transcript is stored beside the recording and never holds up the task (D-062). | S6 M10; R J3.4, J3.10 |
| ASR-010 | AI transcription is optional: an on/off setting per project (default off); when off, no ASR job is created or sent; when on but the Deepgram key is missing, the UI and API show Not configured; the recording and QC workflow is the same either way (D-062). | Owner 2026-11-09 |
| ASR-009 | Labelled reference set per launch language/dialect; WER/CER, speaker-label accuracy if supported, timestamp error, processing time, cost per audio hour; dataset size and method recorded; no claims from tiny samples. | S6 M10; R J4 |

### TRN - Module 11 - Human transcription workspace

Phase: 8 | Requirements: 12

| ID | Requirement | Source |
|---|---|---|
| TRN-001 | WITHDRAWN (D-062): Assigned task queue; a transcriber cannot open or edit another person's task. | S6 M11; R K1 |
| TRN-002 | WITHDRAWN (D-062): Audio player with playback speed, seek and segment navigation. | S6 M11; R K1 |
| TRN-003 | WITHDRAWN (D-062): Transcript editor with speaker labels and timestamp editing. | S6 M11; R K1 |
| TRN-004 | WITHDRAWN (D-062): Draft status, save draft and autosave endpoints; visible save status; draft survives refresh. | S6 M11; R K1 |
| TRN-005 | WITHDRAWN (D-062): Submit endpoint; submission locks the submitted version and moves the task to transcript QC. | S6 M11; R K1 |
| TRN-006 | WITHDRAWN (D-062): Revision history endpoint; prior versions available. | S6 M11; R K1 |
| TRN-007 | WITHDRAWN (D-062): Keyboard shortcuts. | S6 M11; R K1 |
| TRN-008 | WITHDRAWN (D-062): Project transcription rules; verbatim transcription; language-specific scripts. | S6 M11 |
| TRN-009 | WITHDRAWN (D-062): A returned task shows the transcriber the reason and revision request. | S6 M11; R K2 |
| TRN-010 | WITHDRAWN (D-062): Concurrent edits detected. | R K1 |
| TRN-011 | WITHDRAWN (D-062): Autosave failure visible to the user. | R K1 |
| TRN-012 | WITHDRAWN (D-062): Assignment endpoint. | R K1 |

### TQC - Module 12 - Transcript quality control

Phase: 8 | Requirements: 6

| ID | Requirement | Source |
|---|---|---|
| TQC-001 | WITHDRAWN (D-062): Audio and transcript side by side; segment playback. | S6 M12; R K2 |
| TQC-002 | WITHDRAWN (D-062): Edit or annotate if permission allows. | S6 M12 |
| TQC-003 | WITHDRAWN (D-062): Approve, reject, return for correction; a revised transcript creates a new version. | S6 M12; R K2 |
| TQC-004 | WITHDRAWN (D-062): Error categories, reviewer comments, QC history. | S6 M12; R K2 |
| TQC-005 | WITHDRAWN (D-062): Final lock after approval; reopening needs permission, reason and audit entry. | S6 M12; R K2 |
| TQC-006 | WITHDRAWN (D-062): One task completed end to end (recording, audio QC, ASR, human correction, transcript QC, approval) with evidence for each transition. | S11 Gate8; R K3 |

### EXP - Module 13 - Metadata and exports

Phase: 9 | Requirements: 10

| ID | Requirement | Source |
|---|---|---|
| EXP-001 | Export: final WAV, original recordings where permitted, face-to-face recordings, transcript text, timestamped segments, speaker labels, participant IDs, project/task metadata, language/dialect, consent metadata subject to permission, audio QC, processing/model provenance. | S6 M13; R L1 |
| EXP-002 | Formats CSV, TSV, JSON, WAV, ZIP with manifest and checksums. | S6 M13; R L1 |
| EXP-003 | JSON matches its schema. | S6 M13; R L1 |
| EXP-004 | Phone numbers excluded by default; unauthorized data excluded; unauthorized roles cannot export restricted personal data. | S6 M13; R L1.6 |
| EXP-005 | Counts match selected records; ZIP contents match manifest; hashes match. | S6 M13; R L1 |
| EXP-006 | Face-to-face and telephony audio and transcripts in separate folders. | S2 |
| EXP-007 | CSV/TSV open correctly in spreadsheet software. | S6 M13; R L1 |
| EXP-008 | Export filters validated and export permissions checked. | R L1.1-2 |
| EXP-009 | Large exports generated asynchronously; export status stored. | R L1.3, L1.7 |
| EXP-010 | Short-lived download link; export creation and download audited; temporary bundles expire. | R L1.8-10 |

### DASH - Module 14 - Dashboards and reports

Phase: 9 | Requirements: 6

| ID | Requirement | Source |
|---|---|---|
| DASH-001 | Metrics: total tasks, tasks by status, recording hours by mode, daily/monthly target progress, moderator output, QC pass/fail, pending queues, failed calls, failed uploads, storage usage, provider usage and cost estimates. | S6 M14; R L2 |
| DASH-002 | Filters: project, date range, language, dialect, mode, staff, status. | S6 M14; R L2 |
| DASH-003 | Every metric reconciles with an independent SQL query, including date boundaries and timezone handling. | S6 M14; R L2 |
| DASH-004 | Role and project visibility enforced. | S6 M14; R L2 |
| DASH-005 | Provider charges labelled as estimates with rate source and date. | S6 M14 |
| DASH-006 | Empty datasets and large date ranges handled. | R L2 |

### SEC - Module 15 - Audit, privacy and security

Phase: 3, 10 | Requirements: 15

| ID | Requirement | Source |
|---|---|---|
| SEC-001 | Audit log for sensitive actions; audit log integrity reviewed. | S6 M15; R M1 |
| SEC-002 | TLS everywhere. | S6 M15; R M1 |
| SEC-003 | Encryption at rest, including backups. | S6 M15; R M1 |
| SEC-004 | Secret manager; no secrets in frontend code or Git; repository secret scan. | S6 M15, S12.13; R M1 |
| SEC-005 | Rate limits. | S6 M15; R M1 |
| SEC-006 | Input validation. | S6 M15; R M1 |
| SEC-007 | Protection against common web vulnerabilities, including CSRF where cookie auth is used. | S6 M15; R M1 |
| SEC-008 | Backup and restore; restore tested into a test environment. | S6 M15; R M1 |
| SEC-009 | Data retention and deletion enforced. | S6 M15; R M1 |
| SEC-010 | Consent record access controls. | S6 M15 |
| SEC-011 | Role escalation attempts and unauthorized recording downloads fail. | S6 M15; R M1 |
| SEC-012 | Webhook signature failures rejected. | S6 M15; R M1 |
| SEC-013 | Output encoding and secure HTTP headers. | R M1 |
| SEC-014 | Least-privilege cloud roles. | R M1 |
| SEC-015 | Dependency vulnerability scan. | R M1 |

### PWA - Module 16 - PWA installation and usability

Phase: 10 | Requirements: 9

| ID | Requirement | Source |
|---|---|---|
| PWA-001 | manifest.webmanifest with app name, short name, standalone display, theme/background colours, icons in required sizes. | S6 M16; R M2.1-5 |
| PWA-002 | Install prompt where supported; standalone launch. | S6 M16 |
| PWA-003 | Responsive layouts. | S6 M16 |
| PWA-004 | Service worker caches only safe static assets; no private audio or participant data in shared browser storage. | S6 M16; R M2.6-8 |
| PWA-005 | Update detection with reload prompt; a published update reaches the user. | S6 M16; R M2.9 |
| PWA-006 | Offline message for unsupported actions. | S6 M16 |
| PWA-007 | Logout clears sensitive local session state. | S6 M16; R M2.12 |
| PWA-008 | Installation tested on desktop Chrome and a supported mobile browser. | S6 M16; R M2.11 |
| PWA-009 | Install guidance for supported browsers. | R M2.10 |

### OPS - Deployment and operations

Phase: 10 | Requirements: 9

| ID | Requirement | Source |
|---|---|---|
| OPS-001 | Separate local, test/staging and production environments. | R M3 |
| OPS-002 | Deployed components: frontend, backend, PostgreSQL, Redis, workers, private object storage, reverse proxy/ingress, monitoring and logs; infrastructure configuration in the repository. | R M3, M3.1 |
| OPS-003 | Secrets created in a cloud secret manager. | R M3.2 |
| OPS-004 | Database backups and object storage lifecycle configured. | R M3.3-4 |
| OPS-005 | Health checks, TLS, domain and DNS configured. | R M3.5-7 |
| OPS-006 | Monitoring (logs, metrics, error tracking), alerting and log retention configured; alerts work. | S6 M15, S7; R M3.8-9 |
| OPS-007 | Database migrations run as a controlled release step. | R M3.10 |
| OPS-008 | Rollback procedure, disaster recovery runbook and incident runbook exist. | R M3.11-12, R R |
| OPS-009 | Clean deployment reproduced from docs/DEPLOYMENT.md; backup restore tested. | S15; R M3.13-14 |

### LOAD - Capacity and performance testing

Phase: 10 | Requirements: 5

| ID | Requirement | Source |
|---|---|---|
| LOAD-001 | Load test: 50 simultaneous call setups, 50 active conferences, moderator departure from all 50. | S10; R M4 |
| LOAD-002 | 100 participant legs when moderators join by web/VoIP; leg count recalculated if moderators use phone legs. | S10 |
| LOAD-003 | Load test: concurrent recording downloads and uploads, ASR backlog, QC activity, dashboard queries, webhook bursts. | S10 |
| LOAD-004 | 250 recording hours/day (125 per mode) processed. | S10; R M4 |
| LOAD-005 | Report: date, environment, concurrent users/calls, API latency, call setup success, provider concurrency, worker queue delay, upload throughput, storage growth, ASR throughput, database CPU/connections, memory, network, error rates, recording success and integrity, bottlenecks and fixes. | S10; R M4 |

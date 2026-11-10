# Build status

Status vocabulary (runbook A3): NOT STARTED, IN PROGRESS, BLOCKED, IMPLEMENTED — TESTS FAILING,
IMPLEMENTED — AUTOMATED TESTS PASS, VERIFIED, ACCEPTED. VERIFIED needs automated and manual
verification; ACCEPTED needs the phase gate approved. A box is checked only with a real evidence path.

## Modules

"Requirements reviewed = Yes" means the module's requirements are numbered, sourced and each has a
test in TEST_PLAN.md. It does not mean anything is built.

| Module | Prefix | Requirements | Requirements reviewed | Backend | Database | Frontend | Automated tests | Manual test | Status | Blocker |
|---|---|---:|---|---|---|---|---|---|---|---|
| Authentication | AUTH | 16 | Yes | Yes | Yes | Yes | Yes | Yes | IN PROGRESS | Gate 2 approved |
| User management | USER | 9 | Yes | Yes | Yes | Yes | Yes | Yes | IN PROGRESS | Gate 2 approved |
| Roles and permissions | ROLE | 12 | Yes | Yes | Yes | Yes | Yes | Yes | IN PROGRESS | Gate 2 approved |
| Projects | PROJ | 13 | Yes | Yes | Yes | Yes | Yes | Yes | IN PROGRESS | PROJ-010/011 finish in Phases 3 and 9 |
| Participants | PART | 12 | Yes | Yes | Yes | Yes | Yes | Yes | IN PROGRESS | Gate 3 approved |
| Task assignment | TASK | 12 | Yes | Yes | Yes | Yes | Yes | Yes | IN PROGRESS | Gate 3 approved |
| Telephony | TEL | 38 | Yes | No | No | No | No | No | BLOCKED | B-01 provider |
| Face-to-face recording | FTF | 15 | Yes | Yes | Yes | Yes | Yes | Yes | IN PROGRESS | Edge and by-ear playback checks open |
| Storage | STOR | 13 | Yes | Yes | Yes | No | Yes | Yes | IN PROGRESS | Wasabi encryption at rest NOT VERIFIED |
| Audio rules and conversion | AUDIO | 24 | Yes | Yes | Yes | No | Yes | Yes | IN PROGRESS | Telephony parts in Phases 5-6 |
| Audio QC | AQC | 10 | Yes | No | No | No | No | No | NOT STARTED | - |
| AI transcription | ASR | 10 | Yes | No | No | No | No | No | NOT STARTED | - |
| Human transcription | TRN | 12 | Yes | No | No | No | No | No | NOT STARTED | - |
| Transcript QC | TQC | 6 | Yes | No | No | No | No | No | NOT STARTED | - |
| Exports | EXP | 10 | Yes | No | No | No | No | No | NOT STARTED | - |
| Dashboard | DASH | 6 | Yes | No | No | No | No | No | NOT STARTED | - |
| Security and audit | SEC | 15 | Yes | Yes | Yes | Yes | Yes | Partly | IN PROGRESS | Remaining items in Phases 4 and 10 |
| PWA | PWA | 9 | Yes | No | No | No | No | No | NOT STARTED | - |
| Foundation (Phase 1) | FND | 29 | Yes | Yes | Yes | Yes | Yes | Yes | IN PROGRESS | Gate 1 approved; FND-027 done in Phase 2 |
| Database model | DB | 6 | Yes | No | Yes | No | Yes | No | IN PROGRESS | Tables arrive phase by phase |
| Deployment and operations | OPS | 9 | Yes | No | No | No | No | No | NOT STARTED | - |
| Load and performance | LOAD | 5 | Yes | No | No | No | No | No | NOT STARTED | - |
| Capacity and configuration | CAP | 5 | Yes | Yes | Yes | Yes | Yes | No | IN PROGRESS | Load-test parts in Phase 10 |
| Architecture and stack | ARCH | 5 | Yes | No | No | No | Yes | No | IN PROGRESS | Region decision open (B-04) |
| Product scope | PROD | 4 | Yes | No | No | No | No | No | NOT STARTED | - |
| Contract and work rules | GEN | 14 | Yes | No | No | No | Yes | No | IN PROGRESS | Ongoing every phase |
| Build process and tracking | PROC | 9 | Yes | No | No | No | Yes | Yes | IN PROGRESS | Ongoing every phase |
| **Total** | | **328** | | | | | | | | |

## Phases and gates

| Phase | Status | Gate | Gate result |
|---|---|---|---|
| 0 Inspect and plan | ACCEPTED | 0 | Approved by owner 2026-11-09 |
| 1 Foundation | ACCEPTED | 1 | Approved by owner 2026-11-09 |
| 2 Auth, users, roles, projects | ACCEPTED | 2 | Approved by owner 2026-11-09 |
| 3 Participants, tasks, workflow | ACCEPTED | 3 | Approved by owner 2026-11-09 |
| 4 Storage, face-to-face recording | ACCEPTED | 4 | Approved by owner 2026-11-09 (CI run 42652152398 green; Option A fix D-048) |
| 5 Telephony proof of capability | BLOCKED | 5 | B-01: no provider, no credentials |
| 6 Full telephony module | BLOCKED | 6 | Depends on Gate 5 |
| 7 Audio QC, AI transcription | NOT STARTED | 7 | - |
| 8 Human transcription, transcript QC | NOT STARTED | 8 | - |
| 9 Exports, dashboards | NOT STARTED | 9 | - |
| 10 Security, PWA, deployment, operations | NOT STARTED | 10 | - |

## Gate 0 checklist (runbook C0.4, spec Gate 0)

| Condition | Result | Evidence |
|---|---|---|
| Existing repository understood | Pass: new repository, no code before Phase 0 | docs/evidence/phase0/inspection_commands.txt |
| Requirements mapped | Pass: 328 requirements, each with a source and >= 1 test | docs/evidence/phase0/traceability_check.txt |
| Architecture documented | Pass | ARCHITECTURE.md, DATABASE.md, API_CONTRACT.md, SECURITY.md, AUDIO_SPECIFICATION.md, DEPLOYMENT.md |
| Unknowns listed | Pass: B-01..B-12 | DECISIONS.md |
| No existing code deleted | Pass: there was none | docs/evidence/phase0/inspection_commands.txt |
| Tracker contains all modules and requirements | Pass | this file |
| No feature marked complete | Pass: 0 VERIFIED/ACCEPTED | docs/evidence/phase0/traceability_check.txt |
| Required documents exist | Pass | docs/evidence/phase0/doc_check.txt |

## Requirements

| Requirement ID | Description | Phase | Backend | Database | Frontend | Automated test | Manual test | Evidence path | Status | Blocker |
|---|---|---|---|---|---|---|---|---|---|---|
| GEN-001 | Specification and runbook are the binding contract; the whole runbook is read before code changes; no module skipped, silently removed or silently changed. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-01 | docs/evidence/phase1/make_check.txt | IN PROGRESS | Ongoing every phase |
| GEN-002 | No fake data, mocked success, dummy buttons, placeholder pages, stub methods, TODO, FIXME or NotImplemented in production paths or in any feature marked complete; mocks only in isolated tests. | All | n/a | n/a | n/a | [ ] TA-GEN-01 | [ ] TM-GEN-02 | docs/evidence/phase1/make_check.txt | IN PROGRESS | Ongoing every phase |
| GEN-003 | A module is complete only when code exists, the app runs, the feature works, automated tests pass, the manual checklist passes and evidence is in BUILD_STATUS.md. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-03 | - | NOT STARTED | - |
| GEN-004 | A blocked requirement is marked BLOCKED with evidence; provider-independent parts are built behind an adapter or marked boundary; an unconfigured external service shows a truthful Not configured state; nothing pretends to work. | All | n/a | n/a | n/a | [x] TA-GEN-04 | [ ] TM-GEN-03 | docs/evidence/phase4/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| GEN-005 | No invented telephony endpoints, provider features, prices, compliance permissions, audio formats or model capabilities; official documentation URL, access date, feature and test evidence saved in docs/integrations/. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-04 | - | NOT STARTED | - |
| GEN-006 | Evidence per module in docs/evidence/ (files, migrations, API routes, UI routes, tests and results, manual steps and results, screenshots where useful, defects, remaining work, commit hash); no real personal data or secrets in evidence. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-05 | - | NOT STARTED | - |
| GEN-007 | A test not run is reported NOT RUN with the reason and its requirement is not marked verified; unfinished work is INCOMPLETE; undocumented provider claims are NOT VERIFIED. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-05 | - | NOT STARTED | - |
| GEN-008 | No failing tests reported as success; no swallowed exceptions - errors are logged and surfaced. | All | n/a | n/a | n/a | [ ] TA-GEN-02 | [ ] TM-GEN-02 | docs/evidence/phase1/make_check.txt | IN PROGRESS | Ongoing every phase |
| GEN-009 | Existing working code preserved (no delete or rewrite without reason and approval); one small task at a time; when context or time runs out, save state, update the tracker and stop at a clean checkpoint. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-03 | - | NOT STARTED | - |
| GEN-010 | After each task: format, lint, type-check, test, inspect the diff, update the tracker. | All | n/a | n/a | n/a | [ ] TA-GEN-05 | [ ] TM-GEN-05 | docs/evidence/phase1/make_check.txt | IN PROGRESS | Ongoing every phase |
| GEN-011 | Requirement IDs appear in the tracker, in tests, and in code comments where useful. | All | n/a | n/a | n/a | [ ] TA-GEN-06 | n/a | docs/evidence/phase1/make_check.txt | IN PROGRESS | Ongoing every phase |
| GEN-012 | Status vocabulary only: NOT STARTED, IN PROGRESS, BLOCKED, IMPLEMENTED — TESTS FAILING, IMPLEMENTED — AUTOMATED TESTS PASS, VERIFIED, ACCEPTED; VERIFIED needs automated and manual verification; ACCEPTED needs gate approval. | All | n/a | n/a | n/a | [ ] TA-GEN-03 | n/a | docs/evidence/phase1/make_check.txt | IN PROGRESS | Ongoing every phase |
| GEN-013 | No 'fully done' style claims unless the relevant acceptance gate has passed. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-05 | - | NOT STARTED | - |
| GEN-014 | All applicable automated test layers exist: unit, API, database, integration (isolated test doubles), contract (provider mapping against documented schemas), audio fixtures, frontend, end-to-end, security, load; screenshots never replace integration tests. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-07 | - | NOT STARTED | - |
| PROC-001 | Phases run in order; the next phase starts only after the current gate passes; no gate skipped. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-03 | - | NOT STARTED | - |
| PROC-002 | Phase 0 documentation: REQUIREMENTS, REQUIREMENT_TRACEABILITY, ARCHITECTURE, DATABASE, API_CONTRACT, SECURITY, AUDIO_SPECIFICATION, TELEPHONY_PROVIDER_EVALUATION, TEST_PLAN, BUILD_STATUS, DECISIONS, TECH_STACK, DEPLOYMENT, integrations/, evidence/. | All | n/a | n/a | n/a | [x] TA-GEN-07 | [x] TM-GEN-01 | docs/evidence/phase0/doc_check.txt | ACCEPTED | - |
| PROC-003 | Phase 0 inspection commands (pwd, ls -la, find, git status --short, git log -5 --oneline) run and recorded; manifests, dependency files, Docker files, env examples, migrations, tests, CI and deployment config inspected; secret values never printed. | All | n/a | n/a | n/a | n/a | [x] TM-GEN-06 | docs/evidence/phase0/doc_check.txt | ACCEPTED | - |
| PROC-004 | Traceability rows hold ID, requirement, phase, database, API, UI, test, status, evidence. | All | n/a | n/a | n/a | n/a | [x] TM-GEN-01 | docs/evidence/phase0/doc_check.txt | ACCEPTED | - |
| PROC-005 | BUILD_STATUS.md has one row per module and one per requirement (Requirement ID, Description, Phase, Backend, Database, Frontend, Automated test, Manual test, Evidence path, Status, Blocker); every checkbox links to real evidence or stays unchecked; updated every session. | All | n/a | n/a | n/a | [ ] TA-GEN-03 | [ ] TM-GEN-03 | docs/evidence/phase1/make_check.txt | IN PROGRESS | Ongoing every phase |
| PROC-006 | End of every session: git status --short, git diff --check, relevant tests, tracker update, remaining work recorded; commit only if the owner's workflow permits. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-05 | - | NOT STARTED | - |
| PROC-007 | Report after every session/phase in the required format (runbook A2 fields, spec 17 items), with exact commands and files. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-05 | - | NOT STARTED | - |
| PROC-008 | Ask only for truly blocking decisions or credentials; owner approval before major architectural changes or deleting code; stop after Phase 0 and request approval. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-03 | - | NOT STARTED | - |
| PROC-009 | Project called complete or production-ready only when the definition of done (spec 15) and every final release checklist item (runbook R) are met. | All | n/a | n/a | n/a | n/a | [ ] TM-GEN-03 | - | NOT STARTED | - |
| PROD-001 | One cloud-hosted, responsive web application used through a browser. | 1, 10 | n/a | n/a | [ ] | n/a | [ ] TM-PROD-01 | - | NOT STARTED | - |
| PROD-002 | Installable as a PWA from the browser's install option. | 1, 10 | n/a | n/a | [ ] | n/a | [ ] TM-PWA-01 | - | NOT STARTED | - |
| PROD-003 | No native Android or iOS app; participants install nothing; no physical GSM gateway. | 1, 10 | n/a | n/a | [ ] | n/a | [ ] TM-PROD-02 | - | NOT STARTED | - |
| PROD-004 | Two recording modes - telephony and face-to-face - with assets in separate folders/prefixes. | 1, 10 | n/a | n/a | [ ] | [ ] TA-STOR-02 | [ ] TM-PROD-02 | - | NOT STARTED | - |
| CAP-001 | Capacity settings (50 staff, 50 concurrent conferences, 2 participants, 250 h/day, 125 h/day each mode, cloud, web + PWA) stored as editable configuration, not source constants. | 2, 10 | [x] | [x] | [x] | [x] TA-CAP-01, TA-USER-09 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/option_o/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| CAP-002 | An administrator changes targets without a code deployment. | 2, 10 | [x] | [x] | [x] | [x] TA-CAP-02, TA-USER-09 | [ ] TM-CAP-01 | docs/evidence/phase2/make_check.txt; docs/evidence/option_o/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| CAP-003 | Languages configurable per project. | 2, 10 | [x] | [x] | [x] | [x] TA-PROJ-02 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| CAP-004 | Capacity is proven only by a load test plus provider-side concurrency confirmation; never from a local or mock test. | 2, 10 | [ ] | [ ] | [ ] | n/a | [ ] TM-LOAD-01, TM-LOAD-03, TM-TEL-03 | - | NOT STARTED | - |
| CAP-005 | Storage sizing: 115.2 MB/h mono, 230.4 MB/h stereo, 43.2 GB/day at target, 1.296 TB/30 days, about 15.77 TB/year, excluding originals, backups, replicas, metadata and derived copies; retention confirmed before final sizing. | 2, 10 | [ ] | [ ] | [ ] | n/a | [ ] TM-CAP-02 | - | NOT STARTED | - |
| ARCH-001 | Modular monolith first; no unnecessary microservices. | 0, 1 | n/a | n/a | n/a | n/a | [ ] TM-ARCH-01 | - | NOT STARTED | - |
| ARCH-002 | Stack: React + TypeScript, FastAPI, PostgreSQL, Alembic, Celery + Redis, FFmpeg + a tested Python audio library, private S3-compatible storage, Docker, Nginx or managed ingress, web manifest + service worker; Pytest, Vitest/React Testing Library, Playwright; unless the repository already has a functioning equivalent. | 0, 1 | n/a | n/a | n/a | n/a | [ ] TM-ARCH-01 | - | NOT STARTED | - |
| ARCH-003 | Stable versions pinned and recorded in docs/TECH_STACK.md. | 0, 1 | n/a | n/a | n/a | [x] TA-ARCH-01 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| ARCH-004 | Cloud region chosen for data residency, latency and client requirements; recorded as a decision. | 0, 1 | n/a | n/a | n/a | n/a | [ ] TM-ARCH-02 | - | NOT STARTED | - |
| ARCH-005 | Repository inspected before choosing or changing frameworks. | 0, 1 | n/a | n/a | n/a | n/a | [x] TM-GEN-06 | docs/evidence/phase0/doc_check.txt | ACCEPTED | - |
| FND-001 | Backend layout: app/main.py, core/{config,logging,security,errors}.py, api/router.py, db/{base,session}.py, db/migrations/, modules/, tests/, pyproject.toml, Dockerfile. | 1 | [x] | n/a | n/a | n/a | [x] TM-FND-01 | docs/evidence/phase1/manual_checks.txt | VERIFIED | - |
| FND-002 | FastAPI application factory. | 1 | [x] | n/a | n/a | [x] TA-FND-01 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-003 | Configuration from environment variables; required variables validated at startup; invalid configuration prevents unsafe startup. | 1 | [x] | n/a | n/a | [x] TA-FND-02 | n/a | docs/evidence/phase1/make_check.txt; docs/evidence/phase1/manual_checks.txt | VERIFIED | - |
| FND-004 | Structured JSON logging with request IDs and no secrets. | 1 | [x] | n/a | n/a | [x] TA-FND-03 | n/a | docs/evidence/phase1/make_check.txt; docs/evidence/phase1/manual_checks.txt | VERIFIED | - |
| FND-005 | Request ID middleware. | 1 | [x] | n/a | n/a | [x] TA-FND-03 | n/a | docs/evidence/phase1/make_check.txt; docs/evidence/phase1/manual_checks.txt | VERIFIED | - |
| FND-006 | Global exception handlers. | 1 | [x] | n/a | n/a | [x] TA-FND-04 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-007 | /health/live returns success; /health/ready fails clearly when the database is unavailable. | 1 | [x] | n/a | n/a | [x] TA-FND-05 | n/a | docs/evidence/phase1/make_check.txt; docs/evidence/phase1/manual_checks.txt | VERIFIED | - |
| FND-008 | PostgreSQL connection pool. | 1 | [x] | n/a | n/a | [x] TA-FND-06 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-009 | Alembic configured. | 1 | [x] | n/a | n/a | [x] TA-DB-03 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-010 | Separate test database configuration. | 1 | [x] | n/a | n/a | [x] TA-FND-07 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-011 | CORS allowlist from environment variables. | 1 | [x] | n/a | n/a | [x] TA-FND-08 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-012 | API version prefix /api/v1. | 1 | [x] | n/a | n/a | [x] TA-FND-09 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-013 | Frontend layout: src/{app,api,auth,components,features,layouts,routes,styles,test}, public/, package.json, vite.config.ts, tsconfig.json. | 1 | n/a | n/a | [x] | n/a | [x] TM-FND-01 | docs/evidence/phase1/manual_checks.txt | VERIFIED | - |
| FND-014 | React + TypeScript with strict TypeScript; type check passes. | 1 | n/a | n/a | [x] | [x] TA-FND-10 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-015 | Route handling. | 1 | n/a | n/a | [x] | [x] TA-FND-11, TA-FND-17, TA-FND-18 | n/a | docs/evidence/phase1/make_check.txt; docs/evidence/option_c/make_check_frontend.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-016 | Shared API client. | 1 | n/a | n/a | [x] | [x] TA-FND-12, TA-FND-19 | n/a | docs/evidence/phase1/make_check.txt; docs/evidence/phase1/manual_checks.txt; docs/evidence/option_c/make_check_frontend.txt | VERIFIED | - |
| FND-017 | Global error boundary. | 1 | n/a | n/a | [x] | [x] TA-FND-13 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-018 | Loading, empty and error components. | 1 | n/a | n/a | [x] | [x] TA-FND-13, TA-FND-17, TA-FND-19 | n/a | docs/evidence/phase1/make_check.txt; docs/evidence/option_c/make_check_frontend.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-019 | Accessible form controls. | 1 | n/a | n/a | [x] | [x] TA-FND-14, TA-FND-17, TA-FND-19 | n/a | docs/evidence/phase1/make_check.txt; docs/evidence/option_c/make_check_frontend.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-020 | Responsive application shell. | 1 | n/a | n/a | [x] | [x] TA-FND-18 | [x] TM-PWA-02 | docs/evidence/phase1/manual_checks.txt; docs/evidence/phase1/screens/status_375x800.png; docs/evidence/option_c/make_check_frontend.txt | VERIFIED | - |
| FND-021 | Frontend unit test setup; runner passes. | 1 | n/a | n/a | [x] | [x] TA-FND-10 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-022 | Lint and format commands; lint passes. | 1 | n/a | n/a | [x] | [x] TA-FND-10 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-023 | Browser console shows no application errors. | 1 | n/a | n/a | [x] | [x] TA-FND-15 | n/a | docs/evidence/phase1/e2e.txt; docs/evidence/phase1/manual_checks.txt | VERIFIED | - |
| FND-024 | Docker Compose for app, database, Redis and local object storage, with health checks and persistent volumes; one documented command starts dependencies; restart preserves database data. | 1 | [ ] | n/a | [ ] | n/a | [x] TM-FND-02 | docs/evidence/phase1/ci_run.txt | VERIFIED | - |
| FND-025 | .env.example with variable names and safe example values only; .gitignore; no secrets in Git. | 1 | [ ] | n/a | [ ] | [x] TA-SEC-02 | [x] TM-FND-02 | docs/evidence/phase1/ci_run.txt; docs/evidence/phase1/make_check.txt | VERIFIED | - |
| FND-026 | Database migration command; migration runs from an empty database. | 1 | [x] | n/a | n/a | [x] TA-DB-03 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-027 | Development-only seed command for demo accounts; it cannot run in production. | 1 | [x] | n/a | [ ] | [x] TA-FND-16 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt | VERIFIED | - |
| FND-028 | One automated test command; CI runs the same lint, type-check and test commands. | 1 | [ ] | n/a | [ ] | [x] TA-GEN-02 | n/a | docs/evidence/phase1/ci_run.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| FND-029 | Clean setup documented; backend and frontend start from a clean checkout. | 1 | [ ] | n/a | [ ] | n/a | [x] TM-ARCH-03 | docs/evidence/phase1/ci_run.txt | VERIFIED | - |
| DB-001 | Migrations create at least: users, roles, permissions, role_permissions, sessions, password_reset_tokens, projects, project_languages, project_memberships, project_audio_rules, project_transcription_guidelines, project_retention_rules, participants, participant_project_links, consent_records, tasks, task_assignments, task_status_history, task_comments, provider_accounts, call_sessions, call_participants, call_events, provider_webhook_events, recordings, recording_channels, audio_assets, audio_qc_results, transcription_jobs, transcripts, transcript_segments, transcription_assignments, transcript_revisions, transcript_qc_results, exports, audit_logs, system_settings. | 1-9 | n/a | [x] | n/a | [ ] TA-DB-01 | n/a | docs/evidence/phase2/make_check.txt | IN PROGRESS | Tables arrive phase by phase |
| DB-002 | Every table: primary key, foreign keys, unique constraints, indexes from real query patterns, created/updated timestamps, defined deletion behaviour, constrained status values; soft deletion only where appropriate. | 1-9 | n/a | [ ] | n/a | [ ] TA-DB-02 | n/a | docs/evidence/phase1/make_check.txt | IN PROGRESS | Ongoing every phase |
| DB-003 | Schema changes only through migrations; migration tests apply them to an empty database. | 1-9 | n/a | [x] | n/a | [x] TA-DB-03 | n/a | docs/evidence/phase1/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| DB-004 | Workflow state stored in the database, never only in frontend state. | 1-9 | n/a | [ ] | n/a | [ ] TA-TASK-02 | n/a | - | NOT STARTED | - |
| DB-005 | Sensitive columns documented. | 1-9 | n/a | [ ] | n/a | n/a | [ ] TM-DB-01 | - | NOT STARTED | - |
| DB-006 | No binary audio in PostgreSQL; only object-storage keys and metadata. | 1-9 | n/a | [ ] | n/a | [ ] TA-DB-04 | n/a | docs/evidence/phase1/make_check.txt | IN PROGRESS | Ongoing every phase |
| ROLE-001 | Authorization enforced on the backend for every protected API; hidden controls are not security. | 2 | [x] | [x] | [x] | [x] TA-ROLE-01 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt | VERIFIED | - |
| ROLE-002 | Super Admin: full access, system settings and integrations, all users and projects. | 2 | [x] | [x] | [x] | [x] TA-ROLE-01 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| ROLE-003 | Project Admin: assigned projects; create tasks; assign moderators, transcribers and QC staff; view project reports and recordings. | 2 | [x] | [x] | [x] | [x] TA-ROLE-01 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| ROLE-004 | Moderator: assigned tasks only; participant details per project policy; start/control assigned calls; record face-to-face; record consent; submit sessions. | 2 | [x] | [x] | [x] | [x] TA-ROLE-01 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt | VERIFIED | - |
| ROLE-005 | Transcriber: assigned transcription tasks only; play permitted audio; create, edit, submit transcripts. | 2 | [x] | [x] | [x] | [x] TA-ROLE-01 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| ROLE-006 | QC Executive: assigned QC tasks only; review audio and transcripts; pass, fail or return with reason codes and comments. | 2 | [x] | [x] | [x] | [x] TA-ROLE-01 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| ROLE-007 | Client Viewer: read-only, explicitly shared project results only; no internal notes or restricted participant data. | 2 | [x] | [x] | [x] | [x] TA-ROLE-01, TA-ROLE-02 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| ROLE-008 | Permission matrix documented and used as the source of the every-role-against-every-API test. | 2 | [x] | [x] | [x] | [x] TA-SEC-10 | [x] TM-ROLE-01 | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt; docs/evidence/option_b/make_check.txt | VERIFIED | - |
| ROLE-009 | Role and permission constants defined centrally, including users.manage, projects.manage, tasks.assign, calls.start, recordings.view, recordings.download, transcripts.edit, transcripts.review, exports.create, audit.view. | 2 | [x] | [x] | [x] | [x] TA-ROLE-03 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| ROLE-010 | A backend permission dependency is applied to every protected API, with project membership checks. | 2 | [x] | [x] | [x] | [x] TA-ROLE-03, TA-ROLE-01, TA-SEC-10, TA-AUTH-18 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/option_b/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| ROLE-011 | Frontend route and navigation filtering for usability only; changing the route manually does not bypass permissions. | 2 | [x] | [x] | [x] | [x] TA-ROLE-04, TA-FND-17, TA-FND-18 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt; docs/evidence/option_c/make_check_frontend.txt | VERIFIED | - |
| ROLE-012 | Direct API tests per role: moderator cannot call user management; transcriber cannot download an unassigned recording; QC Executive reaches assigned items only; Client Viewer is read-only. | 2 | [x] | [x] | [x] | [x] TA-ROLE-01 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt | VERIFIED | - |
| AUTH-001 | Login with correct credentials succeeds (POST /api/v1/auth/login). | 2 | [x] | [x] | [x] | [x] TA-AUTH-01 | [x] TM-AUTH-01 | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt | VERIFIED | - |
| AUTH-002 | Wrong credentials fail. | 2 | [x] | [x] | [x] | [x] TA-AUTH-02, TA-AUTH-20 | [x] TM-AUTH-01 | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt; docs/evidence/option_b/make_check.txt | VERIFIED | - |
| AUTH-003 | Logout revokes the session on the server (POST /api/v1/auth/logout). | 2 | [x] | [x] | [x] | [x] TA-AUTH-03, TA-AUTH-17 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt; docs/evidence/option_b/make_check.txt | VERIFIED | - |
| AUTH-004 | Password reset with expiring single-use tokens (POST /api/v1/auth/password/forgot, /password/reset). | 2 | [x] | [x] | [x] | [x] TA-AUTH-04, TA-AUTH-20, TA-FND-20 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt; docs/evidence/option_b/make_check.txt; docs/evidence/option_d/journeys.txt | VERIFIED | - |
| AUTH-005 | Session expiry; an expired session requires login. | 2 | [x] | [x] | [x] | [x] TA-AUTH-05, TA-AUTH-18 | [ ] TM-AUTH-01 | docs/evidence/phase2/make_check.txt; docs/evidence/option_b/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| AUTH-006 | Passwords hashed with a modern adaptive algorithm. | 2 | [x] | [x] | [x] | [x] TA-AUTH-06 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| AUTH-007 | Account active/disabled state; disabled users cannot log in. | 2 | [x] | [x] | [x] | [x] TA-AUTH-07 | [ ] TM-AUTH-01 | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| AUTH-008 | Optional multi-factor authentication, added only after the base flow is secure. | 2 | [x] | [x] | [x] | [x] TA-AUTH-08, TA-AUTH-19 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/option_b/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| AUTH-009 | Failed login throttling blocks repeated failures. | 2 | [x] | [x] | [x] | [x] TA-AUTH-09, TA-AUTH-19 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/option_b/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| AUTH-010 | Session and device management, including revocation. | 2 | [x] | [x] | [x] | [x] TA-AUTH-10, TA-AUTH-18, TA-FND-20 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/option_b/make_check.txt; docs/evidence/option_d/journeys.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| AUTH-011 | Role and project access enforced; a moderator cannot open admin APIs by changing a URL or calling the API outside the UI. | 2 | [x] | [x] | [x] | [x] TA-AUTH-11, TA-ROLE-01, TA-SEC-10 | [x] TM-AUTH-01 | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt; docs/evidence/option_b/make_check.txt | VERIFIED | - |
| AUTH-012 | User model with normalized unique email/username. | 2 | [x] | [x] | [x] | [x] TA-AUTH-12 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| AUTH-013 | Secure HTTP-only SameSite cookies (or a documented secure token strategy); no long-lived secrets in browser local storage. | 2 | [x] | [x] | [x] | [x] TA-AUTH-15, TA-AUTH-17 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/option_b/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| AUTH-014 | Audit events for login failures, password changes and account disablement. | 2 | [x] | [x] | [x] | [x] TA-AUTH-13 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| AUTH-015 | GET /api/v1/auth/me returns the current user; no API ever returns a password or hash. | 2 | [x] | [x] | [x] | [x] TA-AUTH-14 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| AUTH-016 | Frontend: login, forgot password, reset password pages, session-expired message, protected route wrapper. | 2 | [x] | [x] | [x] | [x] TA-AUTH-16, TA-FND-17 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt; docs/evidence/option_c/make_check_frontend.txt | VERIFIED | - |
| USER-001 | Create, edit, deactivate and reactivate users. | 2 | [x] | [x] | [x] | [x] TA-USER-01 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt | VERIFIED | - |
| USER-002 | Assign roles. | 2 | [x] | [x] | [x] | [x] TA-USER-02, TA-FND-20 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/option_d/journeys.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| USER-003 | Assign project membership. | 2 | [x] | [x] | [x] | [x] TA-USER-03 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| USER-004 | User list with search, filter and pagination. | 2 | [x] | [x] | [x] | [x] TA-USER-04 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt | VERIFIED | - |
| USER-005 | CSV import with validation preview. | 2 | [x] | [x] | [x] | [x] TA-USER-05 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| USER-006 | CSV export with permission checks (authorized admins only). | 2 | [x] | [x] | [x] | [x] TA-USER-06 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| USER-007 | Every role and membership change audited with who made it. | 2 | [x] | [x] | [x] | [x] TA-USER-07 | [ ] TM-USER-01 | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| USER-008 | A deactivated user loses access immediately or at the next enforced session check. | 2 | [x] | [x] | [x] | [x] TA-USER-08 | [ ] TM-USER-01 | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| USER-009 | One user per role created; each sees only permitted pages and data. | 2 | [x] | [x] | [x] | n/a | [x] TM-USER-01 | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt | VERIFIED | - |
| PROJ-001 | Project create/edit; unique project code and name. | 2 | [x] | [x] | [x] | [x] TA-PROJ-01 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PROJ-002 | Languages and dialects. | 2 | [x] | [x] | [x] | [x] TA-PROJ-02, TA-PROJ-08 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/option_b/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PROJ-003 | Allowed recording modes. | 2 | [x] | [x] | [x] | [x] TA-PROJ-03 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PROJ-004 | Daily recording targets. | 2 | [x] | [x] | [x] | [x] TA-PROJ-03 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PROJ-005 | Audio specification fields. | 2 | [x] | [x] | [x] | [x] TA-PROJ-03 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PROJ-006 | Transcription guidelines with version. | 2 | [x] | [x] | [x] | [x] TA-PROJ-03 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PROJ-007 | QC rules per project. | 2 | [x] | [x] | [x] | [x] TA-PROJ-03, TA-AQC-01 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PROJ-008 | Retention policy. | 2 | [x] | [x] | [x] | [x] TA-PROJ-03 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PROJ-009 | Lifecycle status: draft, active, paused, completed, archived. | 2 | [x] | [x] | [x] | [x] TA-PROJ-04 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PROJ-010 | Archived projects receive no new work unless an authorized admin reopens them. | 2 | [x] | [x] | [ ] | [x] TA-PROJ-05 | n/a | docs/evidence/phase3/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PROJ-011 | Project settings appear in task creation and reports. | 2 | [x] | [ ] | [x] | n/a | [ ] TM-PROJ-01 | docs/evidence/phase3/make_check.txt | IN PROGRESS | Task creation uses project modes; reports in Phase 9 |
| PROJ-012 | Project isolation enforced. | 2 | [x] | [x] | [x] | [x] TA-PROJ-06 | n/a | docs/evidence/phase2/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PROJ-013 | Frontend: project list, create/edit, detail tabs overview, team, audio rules, language, retention. | 2 | [x] | [x] | [x] | [x] TA-PROJ-07 | n/a | docs/evidence/phase2/make_check.txt; docs/evidence/phase2/walkthrough.txt | VERIFIED | - |
| PART-001 | Participant A and B records attached to a task. | 3 | [x] | [x] | [x] | [x] TA-PART-01 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| PART-002 | Unique participant ID from a participant ID generator. | 3 | [x] | [x] | [x] | [x] TA-PART-01 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| PART-003 | Name or approved display label. | 3 | [x] | [x] | [x] | [x] TA-PART-01 | n/a | docs/evidence/phase3/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PART-004 | Phone number for telephony tasks, normalized to one format. | 3 | [x] | [x] | [x] | [x] TA-PART-02 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| PART-005 | Language and dialect. | 3 | [x] | [x] | [x] | [x] TA-PART-01 | n/a | docs/evidence/phase3/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PART-006 | Consent stored separately from the profile: status, method, time, staff member, policy/version; consent audit history. | 3 | [x] | [x] | [x] | [x] TA-PART-03 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| PART-007 | Duplicate participant detection. | 3 | [x] | [x] | [x] | [x] TA-PART-04 | n/a | docs/evidence/phase3/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PART-008 | Restricted personal data; phone numbers visible only with permission, masked otherwise. | 3 | [x] | [x] | [x] | [x] TA-PART-05 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| PART-009 | Retention and deletion support. | 3 | [x] | [x] | [x] | [x] TA-PART-06 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| PART-010 | Only necessary participant details stored. | 3 | [x] | [x] | [x] | n/a | [x] TM-PART-01 | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| PART-011 | Unauthorized users cannot export participant contact details. | 3 | [x] | [x] | [x] | [x] TA-PART-07 | n/a | docs/evidence/phase3/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| PART-012 | Participant correction workflow. | 3 | [x] | [x] | [x] | [x] TA-PART-08 | n/a | docs/evidence/phase3/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| TASK-001 | Create task with project, mode, Participant A, Participant B, target/due date, priority; assign moderator. | 3 | [x] | [x] | [x] | [x] TA-TASK-01 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| TASK-002 | Lifecycle DRAFT -> ASSIGNED -> IN_PROGRESS -> RECORDED -> AUDIO_QC -> TRANSCRIPTION_PENDING -> TRANSCRIPTION_IN_PROGRESS -> TRANSCRIPT_QC -> APPROVED. | 3 | [x] | [x] | [x] | [x] TA-TASK-02 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| TASK-003 | Exception states REJECTED, RETURNED, CANCELLED, ON_HOLD with reason codes. | 3 | [x] | [x] | [x] | [x] TA-TASK-03, TA-FND-20 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt; docs/evidence/option_d/journeys.txt | VERIFIED | - |
| TASK-004 | Invalid or arbitrary state jumps rejected at API level (and in the UI). | 3 | [x] | [x] | [x] | [x] TA-TASK-04 | [x] TM-TASK-01 | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| TASK-005 | Only the assigned moderator sees and starts the task. | 3 | [x] | [x] | [x] | [x] TA-TASK-05 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| TASK-006 | Reassignment requires a reason and creates history. | 3 | [x] | [x] | [x] | [x] TA-TASK-06 | n/a | docs/evidence/phase3/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| TASK-007 | Task comments and history timeline. | 3 | [x] | [x] | [x] | [x] TA-TASK-07 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| TASK-008 | Every state change records user, time and reason. | 3 | [x] | [x] | [x] | [x] TA-TASK-07 | [x] TM-TASK-01 | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| TASK-009 | Allowed statuses and transitions defined in one backend service. | 3 | [x] | [x] | [x] | [x] TA-TASK-08 | n/a | docs/evidence/phase3/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| TASK-010 | State change and its history row written in one database transaction. | 3 | [x] | [x] | [x] | [x] TA-TASK-09 | n/a | docs/evidence/phase3/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| TASK-011 | Task list filters and task detail page. | 3 | [x] | [x] | [x] | [x] TA-TASK-10 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt | VERIFIED | - |
| TASK-012 | Assignment is project-scoped. | 3 | [x] | [x] | [x] | [x] TA-TASK-11 | n/a | docs/evidence/phase3/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| STOR-001 | Private cloud object storage; bucket never public. | 4 | [x] | [x] | [ ] | [x] TA-STOR-01 | [x] TM-STOR-01 | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/wasabi_checks.txt | VERIFIED | - |
| STOR-002 | Object keys: <project>/face-to-face/YYYY/MM/DD/<task>/original/ and /derived/, <project>/telephony/YYYY/MM/DD/<task>/provider-original/ and /final/, <project>/transcripts/<task>/, <project>/metadata/. | 4 | [x] | [x] | [ ] | [x] TA-STOR-02 | n/a | docs/evidence/phase4/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| STOR-003 | Secure upload. | 4 | [x] | [x] | [ ] | [x] TA-STOR-03, TA-STOR-10 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/option_f/storage_contract.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| STOR-004 | Multipart/resumable upload; interrupted upload resumes or restarts safely. | 4 | [x] | [x] | [ ] | [x] TA-STOR-04, TA-STOR-12, TM-STOR-03 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/option_h/make_check.txt; docs/evidence/option_h/database_restart.txt; docs/evidence/option_h/journeys.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| STOR-005 | Download authorization with short-lived signed URLs; no predictable public URLs; expired URL stops working. | 4 | [x] | [x] | [ ] | [x] TA-STOR-05, TA-SEC-10, TA-STOR-10 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/wasabi_checks.txt; docs/evidence/option_b/make_check.txt; docs/evidence/option_f/storage_contract.txt | VERIFIED | - |
| STOR-006 | Upload completion verified; SHA-256 calculated; source and stored checksums compared. | 4 | [x] | [x] | [ ] | [x] TA-STOR-06, TA-STOR-10, TA-STOR-13 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/wasabi_checks.txt; docs/evidence/option_f/storage_contract.txt; docs/evidence/option_o/make_check.txt | VERIFIED | - |
| STOR-007 | Version tracking. | 4 | [x] | [x] | [ ] | [x] TA-STOR-07 | n/a | docs/evidence/phase4/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| STOR-008 | Original and derived assets linked; asset metadata saved in the database. | 4 | [x] | [x] | [ ] | [x] TA-STOR-08 | n/a | docs/evidence/phase4/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| STOR-009 | Retention rules, backup policy, retention and deletion jobs, deletion workflow with audit log. | 4 | [x] | [x] | [ ] | [x] TA-STOR-09, TA-STOR-12 | [ ] TM-STOR-02 | docs/evidence/phase4/make_check.txt; docs/evidence/option_h/make_check.txt; docs/evidence/option_h/database_restart.txt; docs/evidence/option_h/journeys.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| STOR-010 | Storage usage reporting/dashboard. | 4 | [x] | [x] | [ ] | [x] TA-DASH-01, TA-STOR-13 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/option_o/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| STOR-011 | Unauthorized user cannot download a recording. | 4 | [x] | [x] | [ ] | [x] TA-STOR-05, TA-STOR-10 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/wasabi_checks.txt; docs/evidence/option_f/storage_contract.txt | VERIFIED | - |
| STOR-012 | Storage abstraction interface. | 4 | [x] | [x] | [ ] | [x] TA-STOR-10 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/option_f/storage_contract.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| STOR-013 | Server-side encryption configured. | 4 | [ ] | [ ] | [ ] | n/a | [ ] TM-STOR-01 | - | IN PROGRESS | Wasabi encryption at rest NOT VERIFIED (docs check pending) |
| FTF-001 | Browser support check. | 4 | [x] | [x] | [x] | [x] TA-FTF-07 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt | VERIFIED | - |
| FTF-002 | Microphone permission requested after a user action; denial gives a clear error. | 4 | [x] | [x] | [x] | [x] TA-FTF-01 | [x] TM-FTF-02 | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt | VERIFIED | - |
| FTF-003 | Microphones enumerated after permission; moderator selects a device. | 4 | [x] | [x] | [x] | [x] TA-FTF-02 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt | VERIFIED | - |
| FTF-004 | Live input-level meter. | 4 | [x] | [x] | [x] | n/a | [x] TM-FTF-01 | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt | VERIFIED | - |
| FTF-005 | Short test recording and playback. | 4 | [ ] | [ ] | [x] | [x] TA-FTF-10 | [ ] TM-FTF-01 | docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough_channels.txt | IN PROGRESS | Browser plays the delivery file to its end (automated); test playback not yet checked by ear (no speakers on the build machine) |
| FTF-006 | Project audio rules shown before start. | 4 | [x] | [x] | [x] | [x] TA-FTF-08 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt | VERIFIED | - |
| FTF-007 | Start and stop controls; resume; pause only if technically safe. | 4 | [x] | [x] | [x] | [x] TA-FTF-03 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt | VERIFIED | - |
| FTF-008 | Recording duration and state displayed. | 4 | [x] | [x] | [x] | n/a | [x] TM-FTF-01 | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt | VERIFIED | - |
| FTF-009 | Interruption/error events captured; recoverable data preserved where safely possible; accurate recovery message after refresh, tab close or network loss; no claim that recording continues after tab closure or device sleep. | 4 | [x] | [x] | [x] | [x] TA-FND-20, TA-STOR-12 | [x] TM-FTF-03 | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt; docs/evidence/option_d/journeys.txt; docs/evidence/option_h/make_check.txt; docs/evidence/option_h/database_restart.txt; docs/evidence/option_h/journeys.txt | VERIFIED | - |
| FTF-010 | Resumable upload with progress and retry. | 4 | [x] | [x] | [x] | [x] TA-STOR-04, TA-FND-20, TA-STOR-12, TA-FTF-11 | [x] TM-FTF-03 | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt; docs/evidence/option_d/journeys.txt; docs/evidence/option_h/make_check.txt; docs/evidence/option_h/database_restart.txt; docs/evidence/option_h/journeys.txt; docs/evidence/option_o/journeys.txt | VERIFIED | - |
| FTF-011 | Browser capture stored as the original asset. | 4 | [x] | [x] | [x] | [x] TA-STOR-08 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt | VERIFIED | - |
| FTF-012 | Browser echo cancellation, noise suppression and auto gain requested off; applied settings recorded. | 4 | [x] | [x] | [x] | [x] TA-FTF-04 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt | VERIFIED | - |
| FTF-013 | Derived PCM WAV generated and validated. | 4 | [x] | [x] | [x] | [x] TA-FTF-05 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt | VERIFIED | - |
| FTF-014 | Session metadata captured. | 4 | [x] | [x] | [x] | [x] TA-FTF-06 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt | VERIFIED | - |
| FTF-015 | Tested in supported Chrome and Edge versions; a 60-second sample's original and derived files inspected with an independent tool. | 4 | [x] | [x] | [x] | [x] TA-FND-20 | [x] TM-FTF-01 | docs/evidence/phase4/walkthrough.txt; docs/evidence/phase4/walkthrough_channels.txt; docs/evidence/option_d/journeys.txt | IN PROGRESS | Chrome and Microsoft Edge 156 (Linux, CI) verified with fake microphone; 60-second real sample through ffprobe not done (no ffprobe on the build machine); Edge on Windows not tested |
| AUDIO-001 | Telephony: one WAV per conversation. | 4-7 | [ ] | [ ] | [ ] | [ ] TA-AUDIO-01 | n/a | - | NOT STARTED | - |
| AUDIO-002 | Telephony final file: stereo, 16 kHz, 16-bit signed PCM. | 4-7 | [ ] | [ ] | [ ] | [ ] TA-AUDIO-01 | [ ] TM-AUDIO-01 | - | NOT STARTED | - |
| AUDIO-003 | Left channel = Participant A only; right channel = Participant B only. | 4-7 | [ ] | [ ] | [ ] | [ ] TA-AQC-08 | [ ] TM-TEL-02 | - | NOT STARTED | - |
| AUDIO-004 | No noise suppression, normalization, compression, EQ or enhancement in either mode. | 4-7 | [x] | [ ] | [x] | [ ] TA-AUDIO-02, TA-FTF-04 | n/a | docs/evidence/phase4/e2e.txt; docs/evidence/phase4/walkthrough.txt | IN PROGRESS | Face-to-face verified; telephony in Phase 6 |
| AUDIO-005 | No lossy compression in the stored final WAV. | 4-7 | [ ] | [ ] | [ ] | [ ] TA-AUDIO-01 | n/a | - | NOT STARTED | - |
| AUDIO-006 | Provider 'stereo' / 'dual-channel' claims verified on the actual file. | 4-7 | [ ] | [ ] | [ ] | n/a | [ ] TM-TEL-02 | - | NOT STARTED | - |
| AUDIO-007 | No leakage of A into B's channel or B into A's. | 4-7 | [ ] | [ ] | [ ] | [ ] TA-AQC-09 | [ ] TM-TEL-02 | - | NOT STARTED | - |
| AUDIO-008 | Moderator introduction excluded from the participant conversation or stored as a separate consent/introduction recording, per the agreed policy. | 4-7 | [ ] | [ ] | [ ] | n/a | [ ] TM-TEL-02 | - | NOT STARTED | - |
| AUDIO-009 | Recording continues after moderator departure. | 4-7 | [ ] | [ ] | [ ] | n/a | [ ] TM-TEL-02 | - | NOT STARTED | - |
| AUDIO-010 | Both participant tracks aligned in time. | 4-7 | [ ] | [ ] | [ ] | [ ] TA-AUDIO-03 | [ ] TM-TEL-02 | - | NOT STARTED | - |
| AUDIO-011 | A mixed mono recording is never copied into left and right; the requirement is marked BLOCKED/unsupported. | 4-7 | [ ] | [ ] | [ ] | [ ] TA-AUDIO-04, TA-AQC-10 | n/a | - | NOT STARTED | - |
| AUDIO-012 | Separate tracks combined into stereo without altering content; provider originals preserved; every derived-file operation recorded. | 4-7 | [ ] | [ ] | [ ] | [ ] TA-AUDIO-02, TA-STOR-08 | n/a | - | NOT STARTED | - |
| AUDIO-013 | Actual provider codec and recording specification recorded; no 'uncompressed end-to-end' or native 16 kHz claim for a phone call without provider proof. | 4-7 | [ ] | [ ] | [ ] | [ ] TA-AUDIO-05 | [ ] TM-TEL-04 | - | NOT STARTED | - |
| AUDIO-014 | Face-to-face derived target: WAV, mono, 16 000 Hz, 16-bit signed PCM. | 4-7 | [x] | [x] | [ ] | [x] TA-FTF-05 | [x] TM-FTF-01 | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/wasabi_checks.txt | VERIFIED | - |
| AUDIO-015 | Original browser capture kept; converted file is a derived asset with conversion details; never described as untouched original. | 4-7 | [x] | [x] | [ ] | [x] TA-STOR-08, TA-FTF-05, TA-STOR-11 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/wasabi_checks.txt; docs/evidence/phase4/walkthrough_channels.txt | VERIFIED | - |
| AUDIO-016 | Microphone capture needs HTTPS, user permission and a supported browser; clear microphone test before recording. | 4-7 | [ ] | [ ] | [x] | n/a | [x] TM-FTF-01 | docs/evidence/phase4/walkthrough.txt | VERIFIED | - |
| AUDIO-017 | Every final asset stores: extension and actual container, codec/sample format, sample rate, bit depth, channels, duration, size, peak, clipping count or %, silence %, RMS, hash, source recording ID, processing history. | 4-7 | [x] | [x] | [ ] | [x] TA-AUDIO-06 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/wasabi_checks.txt | VERIFIED | - |
| AUDIO-018 | QC analysis never modifies source audio. | 4-7 | [x] | [ ] | [ ] | [ ] TA-AQC-11 | n/a | docs/evidence/phase4/make_check.txt | IN PROGRESS | Measurements read-only; full QC in Phase 7 |
| AUDIO-019 | Deterministic, tested processing pipeline. | 4-7 | [x] | [x] | [ ] | [x] TA-AUDIO-07 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/wasabi_checks.txt | VERIFIED | - |
| AUDIO-020 | Actual original inspected before conversion; decoded without noise reduction or enhancement; resampled to 16 kHz with a documented high-quality resampler; converted to signed 16-bit; written as WAV; original never overwritten. | 4-7 | [x] | [x] | [ ] | [x] TA-FTF-05, TA-AUDIO-08 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/wasabi_checks.txt | VERIFIED | - |
| AUDIO-021 | Conversion to mono only when source channel handling is understood; exact downmix method documented. | 4-7 | [x] | [x] | [ ] | [x] TA-AUDIO-09, TA-FTF-09 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/walkthrough_channels.txt | VERIFIED | - |
| AUDIO-022 | Processing tool, version, parameters and checksum stored for every derived file. | 4-7 | [x] | [x] | [ ] | [x] TA-AUDIO-06 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/phase4/wasabi_checks.txt | VERIFIED | - |
| AUDIO-023 | Independent inspection with ffprobe (-v error -show_streams -show_format) or equivalent. | 4-7 | [x] | [ ] | [ ] | n/a | [x] TM-AUDIO-01 | docs/evidence/phase4/wasabi_checks.txt | IN PROGRESS | libsndfile check done; ffprobe check runs in CI |
| AUDIO-024 | Stereo join of separate tracks used only for genuinely separate, aligned tracks, tested on controlled fixtures first. | 4-7 | [ ] | [ ] | [ ] | [ ] TA-AUDIO-02 | n/a | - | NOT STARTED | - |
| TEL-001 | All provider code behind one adapter interface (internal names, e.g. start_call_to_a, add_b_to_conference, join_moderator, start_recording, moderator_leave, end_conference, get_recording, verify_webhook); real calls implemented only from verified official documentation. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-01 | n/a | - | BLOCKED | B-01 provider |
| TEL-002 | Create outbound call to Participant A. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-02 | [ ] TM-TEL-01 | - | BLOCKED | B-01 provider |
| TEL-003 | Add Participant B to the same conference. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-02 | [ ] TM-TEL-01 | - | BLOCKED | B-01 provider |
| TEL-004 | Join moderator to the conference. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-02 | [ ] TM-TEL-01 | - | BLOCKED | B-01 provider |
| TEL-005 | Mute/unmute. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-02 | [ ] TM-TEL-01 | - | BLOCKED | B-01 provider |
| TEL-006 | Moderator leaves the conference. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-02 | [ ] TM-TEL-01 | - | BLOCKED | B-01 provider |
| TEL-007 | End participant conference. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-02 | [ ] TM-TEL-01 | - | BLOCKED | B-01 provider |
| TEL-008 | Start/stop recording when the provider requires explicit control. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-02 | [ ] TM-TEL-01 | - | BLOCKED | B-01 provider |
| TEL-009 | Receive call and recording webhooks. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-02 | [ ] TM-TEL-01 | - | BLOCKED | B-01 provider |
| TEL-010 | Retrieve recording metadata and files. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-02 | [ ] TM-TEL-01 | - | BLOCKED | B-01 provider |
| TEL-011 | Handle provider errors, timeouts and retries. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-02 | n/a | - | BLOCKED | B-01 provider |
| TEL-012 | Verify webhook signatures; never trust an unsigned webhook. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-03 | n/a | - | BLOCKED | B-01 provider |
| TEL-013 | Unique constraint on provider event ID; idempotent processing; duplicate webhooks create no duplicate sessions or files. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-04 | n/a | - | BLOCKED | B-01 provider |
| TEL-014 | Call sequence implemented in the provider-allowed order: session + conference ID, call A, add B, moderator joins, consent, recording, moderator leaves, bridge continues, close, final event, secure download and validation, audio QC; no invented endpoints. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-05 | [ ] TM-TEL-01 | - | BLOCKED | B-01 provider |
| TEL-015 | No participant conversation recorded before required consent for A and B is recorded. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-06 | n/a | - | BLOCKED | B-01 provider |
| TEL-016 | Participant recording begins at the configured point. | 5, 6 | [ ] | [ ] | [ ] | n/a | [ ] TM-TEL-02 | - | BLOCKED | B-01 provider |
| TEL-017 | Recording retrieval: recording ID validated against the session; fetched through the authenticated provider API; original saved; type and codec inspected; separate tracks retrieved; A/B mapped; final stereo built and validated; checksums and processing metadata saved; task ready for audio QC only after successful validation. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-07, TA-TEL-18 | n/a | - | BLOCKED | B-01 provider |
| TEL-018 | Failed calls visible and recoverable; call event history kept. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-08 | n/a | - | BLOCKED | B-01 provider |
| TEL-019 | Provider acceptance: A and B stay connected after moderator leaves; recording continues; A and B recorded independently; channel mapping correct; recording retrievable through the API. | 5, 6 | [ ] | [ ] | [ ] | n/a | [ ] TM-TEL-02 | - | BLOCKED | B-01 provider |
| TEL-020 | 50 simultaneous conferences supported by the purchased account, confirmed in writing, and tested. | 5, 6 | [ ] | [ ] | [ ] | n/a | [ ] TM-TEL-03, TM-LOAD-01 | - | BLOCKED | B-01 provider |
| TEL-021 | At least two providers compared from official documentation and written answers: India outbound, API call creation, conference creation, add participant to active conference, moderator departure without ending, recording continues, separate tracks or verified dual-channel, recording retrieval API, webhooks and signatures, 50 concurrent conferences, call-leg limits, recording format/sample rate, retention and storage, per-minute and fixed costs, contract and compliance (incl. recording consent). | 5, 6 | [ ] | [ ] | [ ] | n/a | [ ] TM-TEL-04 | - | BLOCKED | B-01 provider |
| TEL-022 | No provider selected on a cheap advertised plan or marketing page. | 5, 6 | [ ] | [ ] | [ ] | n/a | [ ] TM-TEL-04 | - | BLOCKED | B-01 provider |
| TEL-023 | A provider failing any critical item is not accepted; telephony stays BLOCKED, alternatives presented, unrelated modules continue, no fake integration, no quiet workflow substitution. | 5, 6 | [ ] | [ ] | [ ] | n/a | [ ] TM-TEL-02 | - | BLOCKED | B-01 provider |
| TEL-024 | Full telephony UI not built before the proof of capability passes. | 5, 6 | [ ] | [ ] | [ ] | n/a | [ ] TM-GEN-03 | - | BLOCKED | B-01 provider |
| TEL-025 | Isolated proof-of-concept with test credentials stored server-side; test call IDs, provider event IDs and files saved as non-sensitive evidence. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-SEC-02 | [ ] TM-TEL-02 | - | BLOCKED | B-01 provider |
| TEL-026 | Audio acceptance: A says 'This is participant A.', B says 'This is participant B.'; left alone, right alone, both, leakage, alignment, duration, sample rate, bit depth, PCM codec and moderator presence inspected; a mixed-only result fails. | 5, 6 | [ ] | [ ] | [ ] | n/a | [ ] TM-TEL-02 | - | BLOCKED | B-01 provider |
| TEL-027 | Domain model stores task ID, provider call ID, conference ID, participant role (A, B, moderator), call state, start/end times, consent status, recording state, provider event IDs, failure code and safe diagnostics. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-09 | n/a | - | BLOCKED | B-01 provider |
| TEL-028 | Server-side call states CREATED, CALLING_A, A_CONNECTED, ADDING_B, B_CONNECTED, MODERATOR_CONNECTED, CONSENT_PENDING, CONSENT_CONFIRMED, RECORDING, MODERATOR_LEFT, PARTICIPANTS_CONTINUING, COMPLETED, FAILED, CANCELLED; invalid transitions fail safely. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-05 | n/a | - | BLOCKED | B-01 provider |
| TEL-029 | If A or B refuses consent the session ends or is cancelled per project policy. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-10 | n/a | - | BLOCKED | B-01 provider |
| TEL-030 | Moderator departure does not end the conference; only an authorized action ends it. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-11 | [ ] TM-TEL-02 | - | BLOCKED | B-01 provider |
| TEL-031 | Late and out-of-order webhooks handled correctly. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-12 | n/a | - | BLOCKED | B-01 provider |
| TEL-032 | Webhooks acknowledged quickly; heavy work processed asynchronously; raw event metadata stored safely. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-16 | n/a | - | BLOCKED | B-01 provider |
| TEL-033 | Transient webhook failures retried; permanent failures go to a dead-letter queue. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-13 | n/a | - | BLOCKED | B-01 provider |
| TEL-034 | Admin webhook event viewer. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-15 | n/a | - | BLOCKED | B-01 provider |
| TEL-035 | Recording never downloaded from an arbitrary URL in a webhook without validation. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-14 | n/a | - | BLOCKED | B-01 provider |
| TEL-036 | Moderator call UI: assigned task, A/B details, start call, call state, add B, consent checklist for A and B, recording state, leave conference, permission-restricted end session, error/retry display, event timeline. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-17 | [ ] TM-TEL-05 | - | BLOCKED | B-01 provider |
| TEL-037 | Every call UI action goes to the backend and shows the actual provider response; no optimistic 'connected' state. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-17 | n/a | - | BLOCKED | B-01 provider |
| TEL-038 | Failure scenarios handled: A no answer, B no answer, B fails to join, moderator drops, participant disconnects, webhook repeats, webhook out of order, retrieval fails and retries, corrupt recording, one channel missing, 50 concurrent sessions. | 5, 6 | [ ] | [ ] | [ ] | [ ] TA-TEL-19 | [ ] TM-TEL-06, TM-LOAD-01 | - | BLOCKED | B-01 provider |
| AQC-001 | Project-configured thresholds; initial rule flags silence above 25 %; no hard-coded universal thresholds without evidence. | 7 | [ ] | [ ] | [ ] | [ ] TA-AQC-01 | n/a | - | NOT STARTED | - |
| AQC-002 | Checks container, codec, sample rate, bit depth, channels, duration, file size. | 7 | [ ] | [ ] | [ ] | [ ] TA-AQC-02, TA-AQC-03, TA-AQC-04 | n/a | - | NOT STARTED | - |
| AQC-003 | Measures silence ratio, clipping ratio, RMS, peak, dynamic range. | 7 | [ ] | [ ] | [ ] | [ ] TA-AQC-05, TA-AQC-06 | n/a | - | NOT STARTED | - |
| AQC-004 | SNR only with a validated method; otherwise null with reason. | 7 | [ ] | [ ] | [ ] | [ ] TA-AQC-07 | n/a | - | NOT STARTED | - |
| AQC-005 | Channel leakage indicator for stereo telephony. | 7 | [ ] | [ ] | [ ] | [ ] TA-AQC-09 | n/a | - | NOT STARTED | - |
| AQC-006 | Missing, corrupt or undecodable audio detected (decode errors recorded). | 7 | [ ] | [ ] | [ ] | [ ] TA-AQC-12 | n/a | - | NOT STARTED | - |
| AQC-007 | Duplicate audio detection (hash and content). | 7 | [ ] | [ ] | [ ] | [ ] TA-AQC-13 | n/a | - | NOT STARTED | - |
| AQC-008 | Outcome PASS, FAIL or NEEDS_REVIEW with reason code, comment, timestamp and reviewer ID. | 7 | [ ] | [ ] | [ ] | [ ] TA-AQC-14 | n/a | - | NOT STARTED | - |
| AQC-009 | Read-only analysis service; never modifies the source. | 7 | [ ] | [ ] | [ ] | [ ] TA-AQC-11 | n/a | - | NOT STARTED | - |
| AQC-010 | Fixture tests: valid mono, valid stereo, wrong sample rate, wrong bit depth, wrong channel count, silence, clipping, corrupt, swapped channels, identical left/right mixed tracks, missing track. | 7 | [ ] | [ ] | [ ] | [ ] TA-AQC-02, TA-AQC-03, TA-AQC-04, TA-AQC-05, TA-AQC-06, TA-AQC-08, TA-AQC-10, TA-AQC-12, TA-AQC-15 | n/a | - | NOT STARTED | - |
| ASR-001 | Provider-neutral ASR interface: submit job, get status, retrieve result, cancel if supported. | 7 | [ ] | [ ] | [ ] | [ ] TA-ASR-01 | n/a | - | NOT STARTED | - |
| ASR-002 | AI transcription provider: Deepgram (owner decision 2026-11-09, replaces the spec's initial candidates Whisper Large-v3 / AI4Bharat); its capabilities, models, language coverage and prices used only after official-documentation check and evaluation; other providers only after evaluation. | 7 | [ ] | [ ] | [ ] | n/a | [ ] TM-ASR-01 | - | NOT STARTED | - |
| ASR-003 | Audio queued for transcription after it passes audio QC. | 7 | [ ] | [ ] | [ ] | [ ] TA-ASR-02, TA-ASR-07 | n/a | - | NOT STARTED | - |
| ASR-004 | Language and dialect selected per job. | 7 | [ ] | [ ] | [ ] | [ ] TA-ASR-02 | n/a | - | NOT STARTED | - |
| ASR-005 | Stored per job: provider/model name, exact version, language, settings, source asset ID, status, start/end times, raw response, normalized transcript, error details. | 7 | [ ] | [ ] | [ ] | [ ] TA-ASR-03 | n/a | - | NOT STARTED | - |
| ASR-006 | Timestamps, speaker labels and confidence stored only when the model returns them; otherwise null. | 7 | [ ] | [ ] | [ ] | [ ] TA-ASR-04 | n/a | - | NOT STARTED | - |
| ASR-007 | Bounded retries; permanent failure visible to admin. | 7 | [ ] | [ ] | [ ] | [ ] TA-ASR-05 | n/a | - | NOT STARTED | - |
| ASR-008 | Worker fetches audio through an authorized service; human review task created; AI and human transcripts compared. | 7 | [ ] | [ ] | [ ] | [ ] TA-ASR-06, TA-ASR-07 | n/a | - | NOT STARTED | - |
| ASR-010 | AI transcription is optional: an on/off setting per project (default off); when off, no ASR job is created or sent and human transcription starts from an empty transcript; when on but the Deepgram key is missing, the UI and API show Not configured and work falls back to human transcription. | 7 | [ ] | [ ] | [ ] | [ ] TA-ASR-08, TA-GEN-04 | n/a | - | NOT STARTED | - |
| ASR-009 | Labelled reference set per launch language/dialect; WER/CER, speaker-label accuracy if supported, timestamp error, processing time, cost per audio hour; dataset size and method recorded; no claims from tiny samples. | 7 | [ ] | [ ] | [ ] | n/a | [ ] TM-ASR-02 | - | NOT STARTED | - |
| TRN-001 | Assigned task queue; a transcriber cannot open or edit another person's task. | 8 | [ ] | [ ] | [ ] | [ ] TA-TRN-01 | n/a | - | NOT STARTED | - |
| TRN-002 | Audio player with playback speed, seek and segment navigation. | 8 | [ ] | [ ] | [ ] | n/a | [ ] TM-TRN-01 | - | NOT STARTED | - |
| TRN-003 | Transcript editor with speaker labels and timestamp editing. | 8 | [ ] | [ ] | [ ] | [ ] TA-TRN-02 | n/a | - | NOT STARTED | - |
| TRN-004 | Draft status, save draft and autosave endpoints; visible save status; draft survives refresh. | 8 | [ ] | [ ] | [ ] | [ ] TA-TRN-03 | [ ] TM-TRN-01 | - | NOT STARTED | - |
| TRN-005 | Submit endpoint; submission locks the submitted version and moves the task to transcript QC. | 8 | [ ] | [ ] | [ ] | [ ] TA-TRN-04 | n/a | - | NOT STARTED | - |
| TRN-006 | Revision history endpoint; prior versions available. | 8 | [ ] | [ ] | [ ] | [ ] TA-TRN-05 | n/a | - | NOT STARTED | - |
| TRN-007 | Keyboard shortcuts. | 8 | [ ] | [ ] | [ ] | n/a | [ ] TM-TRN-01 | - | NOT STARTED | - |
| TRN-008 | Project transcription rules; verbatim transcription; language-specific scripts. | 8 | [ ] | [ ] | [ ] | [ ] TA-TRN-06 | n/a | - | NOT STARTED | - |
| TRN-009 | A returned task shows the transcriber the reason and revision request. | 8 | [ ] | [ ] | [ ] | [ ] TA-TRN-07 | n/a | - | NOT STARTED | - |
| TRN-010 | Concurrent edits detected. | 8 | [ ] | [ ] | [ ] | [ ] TA-TRN-08 | n/a | - | NOT STARTED | - |
| TRN-011 | Autosave failure visible to the user. | 8 | [ ] | [ ] | [ ] | [ ] TA-TRN-09 | n/a | - | NOT STARTED | - |
| TRN-012 | Assignment endpoint. | 8 | [ ] | [ ] | [ ] | [ ] TA-TRN-01 | n/a | - | NOT STARTED | - |
| TQC-001 | Audio and transcript side by side; segment playback. | 8 | [ ] | [ ] | [ ] | n/a | [ ] TM-TQC-01 | - | NOT STARTED | - |
| TQC-002 | Edit or annotate if permission allows. | 8 | [ ] | [ ] | [ ] | [ ] TA-TQC-01 | n/a | - | NOT STARTED | - |
| TQC-003 | Approve, reject, return for correction; a revised transcript creates a new version. | 8 | [ ] | [ ] | [ ] | [ ] TA-TQC-02 | n/a | - | NOT STARTED | - |
| TQC-004 | Error categories, reviewer comments, QC history. | 8 | [ ] | [ ] | [ ] | [ ] TA-TQC-03 | n/a | - | NOT STARTED | - |
| TQC-005 | Final lock after approval; reopening needs permission, reason and audit entry. | 8 | [ ] | [ ] | [ ] | [ ] TA-TQC-04 | n/a | - | NOT STARTED | - |
| TQC-006 | One task completed end to end (recording, audio QC, ASR, human correction, transcript QC, approval) with evidence for each transition. | 8 | [ ] | [ ] | [ ] | n/a | [ ] TM-TQC-02 | - | NOT STARTED | - |
| EXP-001 | Export: final WAV, original recordings where permitted, face-to-face recordings, transcript text, timestamped segments, speaker labels, participant IDs, project/task metadata, language/dialect, consent metadata subject to permission, audio QC, transcript QC, processing/model provenance. | 9 | [ ] | [ ] | [ ] | [ ] TA-EXP-01 | n/a | - | NOT STARTED | - |
| EXP-002 | Formats CSV, TSV, JSON, WAV, ZIP with manifest and checksums. | 9 | [ ] | [ ] | [ ] | [ ] TA-EXP-02 | n/a | - | NOT STARTED | - |
| EXP-003 | JSON matches its schema. | 9 | [ ] | [ ] | [ ] | [ ] TA-EXP-03 | n/a | - | NOT STARTED | - |
| EXP-004 | Phone numbers excluded by default; unauthorized data excluded; unauthorized roles cannot export restricted personal data. | 9 | [ ] | [ ] | [ ] | [ ] TA-EXP-04 | n/a | - | NOT STARTED | - |
| EXP-005 | Counts match selected records; ZIP contents match manifest; hashes match. | 9 | [ ] | [ ] | [ ] | [ ] TA-EXP-05 | n/a | - | NOT STARTED | - |
| EXP-006 | Face-to-face and telephony audio and transcripts in separate folders. | 9 | [ ] | [ ] | [ ] | [ ] TA-EXP-06 | n/a | - | NOT STARTED | - |
| EXP-007 | CSV/TSV open correctly in spreadsheet software. | 9 | [ ] | [ ] | [ ] | n/a | [ ] TM-EXP-01 | - | NOT STARTED | - |
| EXP-008 | Export filters validated and export permissions checked. | 9 | [ ] | [ ] | [ ] | [ ] TA-EXP-07 | n/a | - | NOT STARTED | - |
| EXP-009 | Large exports generated asynchronously; export status stored. | 9 | [ ] | [ ] | [ ] | [ ] TA-EXP-08 | n/a | - | NOT STARTED | - |
| EXP-010 | Short-lived download link; export creation and download audited; temporary bundles expire. | 9 | [ ] | [ ] | [ ] | [ ] TA-EXP-09 | n/a | - | NOT STARTED | - |
| DASH-001 | Metrics: total tasks, tasks by status, recording hours by mode, daily/monthly target progress, moderator and transcriber output, QC pass/fail, pending queues, failed calls, failed uploads, storage usage, provider usage and cost estimates. | 9 | [ ] | [ ] | [ ] | [ ] TA-DASH-01 | n/a | - | NOT STARTED | - |
| DASH-002 | Filters: project, date range, language, dialect, mode, staff, status. | 9 | [ ] | [ ] | [ ] | [ ] TA-DASH-02 | n/a | - | NOT STARTED | - |
| DASH-003 | Every metric reconciles with an independent SQL query, including date boundaries and timezone handling. | 9 | [ ] | [ ] | [ ] | [ ] TA-DASH-03 | n/a | - | NOT STARTED | - |
| DASH-004 | Role and project visibility enforced. | 9 | [ ] | [ ] | [ ] | [ ] TA-DASH-04 | n/a | - | NOT STARTED | - |
| DASH-005 | Provider charges labelled as estimates with rate source and date. | 9 | [ ] | [ ] | [ ] | n/a | [ ] TM-DASH-01 | - | NOT STARTED | - |
| DASH-006 | Empty datasets and large date ranges handled. | 9 | [ ] | [ ] | [ ] | [ ] TA-DASH-05 | n/a | - | NOT STARTED | - |
| SEC-001 | Audit log for sensitive actions; audit log integrity reviewed. | 3, 10 | [x] | [x] | [x] | [ ] TA-SEC-01, TA-FND-20 | [x] TM-SEC-06 | docs/evidence/phase3/make_check.txt; docs/evidence/phase3/walkthrough.txt; docs/evidence/option_d/journeys.txt | IN PROGRESS | Integrity review (TM-SEC-06) in Phase 10 |
| SEC-002 | TLS everywhere. | 3, 10 | [ ] | [ ] | [ ] | n/a | [ ] TM-SEC-01 | - | NOT STARTED | - |
| SEC-003 | Encryption at rest, including backups. | 3, 10 | [ ] | [ ] | [ ] | n/a | [ ] TM-SEC-01 | - | NOT STARTED | - |
| SEC-004 | Secret manager; no secrets in frontend code or Git; repository secret scan. | 3, 10 | [ ] | [ ] | [ ] | [ ] TA-SEC-02 | n/a | docs/evidence/phase1/make_check.txt | IN PROGRESS | CI run pending |
| SEC-005 | Rate limits. | 3, 10 | [x] | [x] | [ ] | [x] TA-SEC-03 | n/a | docs/evidence/phase3/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| SEC-006 | Input validation. | 3, 10 | [x] | [x] | [ ] | [x] TA-SEC-04, TA-SEC-12, TA-SEC-14 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/option_b/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| SEC-007 | Protection against common web vulnerabilities, including CSRF where cookie auth is used. | 3, 10 | [x] | [x] | [ ] | [ ] TA-SEC-05, TA-SEC-10, TA-SEC-11, TA-SEC-12 | [ ] TM-SEC-02 | docs/evidence/phase2/make_check.txt; docs/evidence/option_b/make_check.txt | IN PROGRESS | Automated CSRF, SQL-injection and cross-project checks done (Option B); browser XSS and web scan in Phase 10 |
| SEC-008 | Backup and restore; restore tested into a test environment. | 3, 10 | [ ] | [ ] | [ ] | [x] TA-STOR-14 | [ ] TM-SEC-03 | docs/evidence/option_o/make_check.txt | NOT STARTED | - |
| SEC-009 | Data retention and deletion enforced. | 3, 10 | [ ] | [ ] | [ ] | [ ] TA-STOR-09, TA-PART-06 | n/a | - | NOT STARTED | - |
| SEC-010 | Consent record access controls. | 3, 10 | [x] | [x] | [ ] | [x] TA-SEC-06, TA-SEC-10 | n/a | docs/evidence/phase3/make_check.txt; docs/evidence/option_b/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| SEC-011 | Role escalation attempts and unauthorized recording downloads fail. | 3, 10 | [x] | [ ] | [ ] | [x] TA-SEC-07, TA-STOR-05, TA-SEC-10, TA-SEC-15 | n/a | docs/evidence/phase4/make_check.txt; docs/evidence/option_b/make_check.txt | IMPLEMENTED — AUTOMATED TESTS PASS | - |
| SEC-012 | Webhook signature failures rejected. | 3, 10 | [ ] | [ ] | [ ] | [ ] TA-TEL-03 | n/a | - | NOT STARTED | - |
| SEC-013 | Output encoding and secure HTTP headers. | 3, 10 | [ ] | [ ] | [ ] | [ ] TA-SEC-08, TA-SEC-13, TA-SEC-16 | n/a | docs/evidence/phase1/make_check.txt; docs/evidence/option_b/make_check.txt | IN PROGRESS | Ongoing every phase |
| SEC-014 | Least-privilege cloud roles. | 3, 10 | [ ] | [ ] | [ ] | n/a | [ ] TM-SEC-05 | - | NOT STARTED | - |
| SEC-015 | Dependency vulnerability scan. | 3, 10 | [ ] | [ ] | [ ] | [x] TA-SEC-09 | n/a | docs/evidence/phase1/ci_run.txt | IMPLEMENTED — AUTOMATED TESTS PASS | Moderate dev-only advisory recorded |
| PWA-001 | manifest.webmanifest with app name, short name, standalone display, theme/background colours, icons in required sizes. | 10 | n/a | n/a | [ ] | [ ] TA-PWA-01 | n/a | - | NOT STARTED | - |
| PWA-002 | Install prompt where supported; standalone launch. | 10 | n/a | n/a | [ ] | n/a | [ ] TM-PWA-01 | - | NOT STARTED | - |
| PWA-003 | Responsive layouts. | 10 | n/a | n/a | [ ] | n/a | [ ] TM-PWA-02 | - | NOT STARTED | - |
| PWA-004 | Service worker caches only safe static assets; no private audio or participant data in shared browser storage. | 10 | n/a | n/a | [ ] | [ ] TA-PWA-02 | n/a | - | NOT STARTED | - |
| PWA-005 | Update detection with reload prompt; a published update reaches the user. | 10 | n/a | n/a | [ ] | n/a | [ ] TM-PWA-03 | - | NOT STARTED | - |
| PWA-006 | Offline message for unsupported actions. | 10 | n/a | n/a | [ ] | [ ] TA-PWA-03 | n/a | - | NOT STARTED | - |
| PWA-007 | Logout clears sensitive local session state. | 10 | n/a | n/a | [ ] | [ ] TA-PWA-04 | n/a | - | NOT STARTED | - |
| PWA-008 | Installation tested on desktop Chrome and a supported mobile browser. | 10 | n/a | n/a | [ ] | n/a | [ ] TM-PWA-01 | - | NOT STARTED | - |
| PWA-009 | Install guidance for supported browsers. | 10 | n/a | n/a | [ ] | n/a | [ ] TM-PWA-04 | - | NOT STARTED | - |
| OPS-001 | Separate local, test/staging and production environments. | 10 | n/a | n/a | n/a | n/a | [ ] TM-OPS-01 | - | NOT STARTED | - |
| OPS-002 | Deployed components: frontend, backend, PostgreSQL, Redis, workers, private object storage, reverse proxy/ingress, monitoring and logs; infrastructure configuration in the repository. | 10 | n/a | n/a | n/a | n/a | [ ] TM-OPS-01 | - | NOT STARTED | - |
| OPS-003 | Secrets created in a cloud secret manager. | 10 | n/a | n/a | n/a | n/a | [ ] TM-OPS-02 | - | NOT STARTED | - |
| OPS-004 | Database backups and object storage lifecycle configured. | 10 | n/a | n/a | n/a | [x] TA-STOR-14 | [ ] TM-SEC-03, TM-STOR-02 | docs/evidence/option_o/make_check.txt | NOT STARTED | - |
| OPS-005 | Health checks, TLS, domain and DNS configured. | 10 | n/a | n/a | n/a | n/a | [ ] TM-OPS-02, TM-SEC-01 | - | NOT STARTED | - |
| OPS-006 | Monitoring (logs, metrics, error tracking), alerting and log retention configured; alerts work. | 10 | n/a | n/a | n/a | [x] TA-FND-22 | [ ] TM-SEC-04, TM-OPS-02 | docs/evidence/option_o/make_check.txt | NOT STARTED | - |
| OPS-007 | Database migrations run as a controlled release step. | 10 | n/a | n/a | n/a | n/a | [ ] TM-OPS-03 | - | NOT STARTED | - |
| OPS-008 | Rollback procedure, disaster recovery runbook and incident runbook exist. | 10 | n/a | n/a | n/a | n/a | [ ] TM-OPS-04 | - | NOT STARTED | - |
| OPS-009 | Clean deployment reproduced from docs/DEPLOYMENT.md; backup restore tested. | 10 | n/a | n/a | n/a | n/a | [ ] TM-ARCH-03, TM-SEC-03 | - | NOT STARTED | - |
| LOAD-001 | Load test: 50 simultaneous call setups, 50 active conferences, moderator departure from all 50. | 10 | n/a | n/a | n/a | n/a | [ ] TM-LOAD-01 | - | NOT STARTED | - |
| LOAD-002 | 100 participant legs when moderators join by web/VoIP; leg count recalculated if moderators use phone legs. | 10 | n/a | n/a | n/a | n/a | [ ] TM-LOAD-01, TM-TEL-04 | - | NOT STARTED | - |
| LOAD-003 | Load test: concurrent recording downloads and uploads, ASR backlog, QC activity, dashboard queries, webhook bursts. | 10 | n/a | n/a | n/a | n/a | [x] TM-LOAD-04 (development server only) | docs/evidence/option_g/load_report.txt | IN PROGRESS | Development-server run done (Option G); production run and telephony load in Phase 10 (CAP-004) |
| LOAD-004 | 250 recording hours/day (125 per mode) processed. | 10 | n/a | n/a | n/a | n/a | [ ] TM-LOAD-02 | - | NOT STARTED | - |
| LOAD-005 | Report: date, environment, concurrent users/calls, API latency, call setup success, provider concurrency, worker queue delay, upload throughput, storage growth, ASR throughput, database CPU/connections, memory, network, error rates, recording success and integrity, bottlenecks and fixes. | 10 | n/a | n/a | n/a | n/a | [x] TM-LOAD-04 (development server only) | docs/evidence/option_g/load_report.txt | IN PROGRESS | Development-server run done (Option G); production run and telephony load in Phase 10 (CAP-004) |

## Session log

### Session 1 - 2026-11-09 - Phase 0

- Repository inspected (runbook C0.1 commands): docs/evidence/phase0/inspection_commands.txt, repo_inspection.txt.
- Documents: REQUIREMENTS, REQUIREMENT_TRACEABILITY, ARCHITECTURE, DATABASE, API_CONTRACT, SECURITY,
  AUDIO_SPECIFICATION, TELEPHONY_PROVIDER_EVALUATION, TEST_PLAN, BUILD_STATUS, DECISIONS, TECH_STACK,
  DEPLOYMENT, integrations/README.md, RUNBOOK_SOURCE.md (copy of the runbook).
- Traceability check PASS. Migrations, API routes, UI routes: none. Application tests: NOT RUN (no code).
- Owner approved Phase 0 on 2026-11-09 and named the remote https://github.com/vquad99/CallRecorderDataCollection.
- Commit: see git log (first commit of the repository).
- Remaining: B-08 for Phase 1.
- Owner decision: AI transcription uses Deepgram and is optional per project (ASR-002, ASR-010, D-018).
- Next single task: Phase 1 / D1 - backend application factory with configuration validation.

### Session 2 - 2026-11-09 - Phase 1 (foundation)

- Backend (FastAPI app factory, validated environment config, JSON logs with request IDs and redaction,
  request ID middleware, one error format, /health/live and /health/ready, pooled PostgreSQL engine,
  Alembic with baseline migration 0001 `system_settings`, CORS allowlist, /api/v1 prefix, security headers).
- Frontend (React + strict TypeScript, routes, shared API client, error boundary, loading/empty/error
  states, accessible form controls, responsive shell, system status page, Vitest + Playwright).
- Local environment and CI: infra/docker-compose.yml, Dockerfiles, nginx, .env.example, .gitignore,
  Makefile (`make check`), tools/check_repo.py, .github/workflows/ci.yml.
- Tests: `make check UV=uv` -> repo rules 0 problems, backend 43 passed (DB tests on a private PostgreSQL),
  frontend 21 passed, build OK; `PW_CHANNEL=chrome npx playwright test` -> 1 passed. Evidence: docs/evidence/phase1/.
- NOT RUN here: Docker Compose start, health checks and restart persistence (no Docker on the build
  machine) - run by the CI `compose` job; secret and dependency scans - CI.
- INCOMPLETE: FND-027 demo-account seed needs the users table (Phase 2).
- CI run 42619512800 on commit 65807da: all 4 jobs succeeded - repo rules + secret scan (no leaks),
  backend 43 passed with REQUIRE_DB_TESTS=1 + pip-audit clean, frontend 21 + 1 browser test + build,
  containers (db, redis, storage, backend, web) healthy, migration applied, data kept across a database
  restart. Evidence: docs/evidence/phase1/ci_run.txt.
- Known issue: 1 moderate npm advisory in dev-only lint tooling (minimatch via typescript-eslint).
- Gate 1: every condition met; waiting for owner approval.
- Next single task (after approval): Phase 2 / E1 - users, sessions and login.

### Session 3 - 2026-11-09 - Phase 2 (accounts, roles, projects)

- Owner approved Gate 1 and asked for Phase 2.
- Backend: migration 0002 (users, roles, permissions, role_permissions, user_roles, sessions,
  password_reset_tokens, login_attempts, audit_logs with an append-only trigger, projects and its
  languages / audio rules / guidelines / retention / memberships; roles, permissions and capacity
  targets seeded). Login, logout, session expiry (idle + absolute), CSRF double-submit, Argon2id,
  throttling, password reset and invitations by email, password change, own-session list/revoke,
  optional TOTP two-step sign-in, user admin with CSV import preview and export, projects with
  lifecycle rules, team picker, capacity settings, `python -m app.cli seed-dev`.
- Frontend: sign-in, forgot/reset password, account (password, two-step sign-in, devices), users
  (list, add, edit, import), projects (list, add, six tabs), capacity settings; navigation and routes
  filtered by permission (usability only).
- Tests: backend 97 passed (permission matrix for all six roles, registry = database = documented
  matrix, every non-public route rejects anonymous callers); frontend 37 passed; browser test 1 passed.
  The permission test was proven both ways (removing the settings check made 6 tests fail).
- Manual: real backend + frontend walk-through (docs/evidence/phase2/walkthrough.txt, 10 screenshots).
- Fixed during the session: decimal values shown inconsistently; demo accounts used a domain the
  email checker rejects (D-030); code permissions disagreed with the approved matrix in 3 places (D-029).
- Open: PROJ-010 / PROJ-011 complete in later phases; production email needs an SMTP provider (B-13).
- CI run 42636982501 (commit a34c9b8): all 4 jobs succeeded. The previous run failed only the secret
  scan, on a hard-coded test-only encryption key; tests now generate the key per run.
- Gate 2: every condition met; waiting for owner approval.
- Next single task (after approval): Phase 3 / F1 - participant records, consent and duplicate detection.

### Session 4 - 2026-11-09 - Phase 3 (participants, tasks, workflow, audit)

- Owner approved Gate 2 and asked for Phase 3.
- Backend: migration 0003 (participants, participant_project_links, consent_records, tasks,
  task_assignments, task_status_history, task_comments; code sequences). Participant service with
  E.164 phones encrypted + keyed-hash duplicate detection, three visibility tiers (D-035), corrections,
  deletion that removes personal data (D-038), contact export, consent history. Task service with one
  workflow module (D-037), moderator assignment and reassignment with reason, start by the assigned
  moderator only, hold/resume/cancel with reason codes, consent capture by the assigned moderator,
  comments and timeline; status, history and audit written in one transaction. Audit-log viewer
  (Project Admins see their projects only). Rate limits (D-039).
- Frontend: project Participants tab, Tasks list, New task, Task detail (assign, status with reasons,
  consent, history), Audit log page; navigation adds Tasks and Audit log.
- Tests: backend 121 passed (every one of the 169 status pairs tried through the API; rollback when
  the history write fails; every write route rejects malformed bodies; escalation attempts fail;
  rate limit returns 429); frontend 44 passed; browser test 1 passed.
- Manual: real walk-through with project admin, moderator, transcriber and super admin
  (docs/evidence/phase3/walkthrough.txt, 5 screenshots).
- CI run 42642154629 (commit e8db924): all 4 jobs succeeded on the first run.
- Gate 3: every condition met; waiting for owner approval.
- Next single task (after approval): Phase 4 / G1 - storage adapter (Wasabi / SeaweedFS) and signed URLs.

### Session 5 - 2026-11-09 - Phase 4 (storage, face-to-face recording)

- Owner approved Gate 3 and asked for Phase 4.
- Downloading a standalone FFmpeg was blocked by the build machine's security check; conversion uses
  libsoxr through python-soxr instead (D-040), with libsndfile and (in CI) ffprobe for independent checks.
- Backend: migration 0004 (recordings, recording_chunks, audio_assets, asset_processing_steps); S3
  storage adapter (Wasabi / SeaweedFS); chunked upload with SHA-256 checks and safe retries; interruption,
  completion, discard; processing into the untouched browser original (32-bit float WAV) and the derived
  16 kHz 16-bit mono WAV with a full validation record and processing history; task moves to RECORDED;
  signed play/download links; retention job (`python -m app.cli retention`); live storage usage; Celery
  worker (Redis) or in-process processing; truthful 503 NOT_CONFIGURED without storage.
- Frontend: recorder page (support check, permission, device choice, level meter, test-and-playback,
  timer, 5-second chunk uploads with retry, recovery of an interrupted recording, results and playback).
- Tests: backend 134 passed + 1 NOT RUN locally (ffprobe; runs in CI); frontend 50 passed; browser tests 2
  passed (one records with Chrome's fake microphone).
- Manual: real recording into the Wasabi bucket (dev prefix) with Chrome's fake microphone; browser
  processing confirmed off; Wasabi privacy and link expiry checked; test objects deleted
  (docs/evidence/phase4/).
- Open: Edge not tested (not on this machine); test playback not checked by ear; Wasabi encryption at
  rest not verified from documentation.
- Next single task: push, read CI, then Gate 4 review.

### Session 6 - 2026-11-09 - Phase 4 stabilisation (owner's test list, Option A)

- CI run 42648499520 failed one browser test: when Start was pressed before the capture's first audio
  block arrived, the page sent "mono" while the browser reported 2 channels
  (docs/evidence/phase4/ci_run.txt). The capture also kept only channel 1 inside the browser, so the
  stored "original" was not everything captured.
- Fix (D-048): the original keeps every captured channel byte for byte; only the derived file takes
  channel 1, with no mixing; `device_channel_count`, `channel_count` and the server-set
  `channel_handling` are stored separately and checked against the built file; Start waits for the real
  channel count; a channel-layout change stops capture and keeps what was saved; chunks must hold whole
  frames; a stored original is checked against its SHA-256 before re-use (migration 0005).
- Tests added: two-channel recording end to end (independent reader, spectrum shows channel 2 is not
  mixed in), half-frame and empty chunks refused, damaged stored original refused, original never
  rewritten on reprocessing, stereo WAV wrapper and channel-1 derivation byte-identical to converting
  channel 1 alone, ffprobe of a 2-channel original and its derived file (CI); browser test checks the
  channel facts, whole 5-second chunks and playback of the delivery file to its end; CI now also runs the
  browser tests in Microsoft Edge.
- Results: backend 138 passed + 1 NOT RUN locally (ffprobe; runs in CI); frontend 50 passed; browser
  tests 2 passed in Chrome. Real recording into Wasabi (dev prefix `dev-aws-dev/phase4-recheck/`) with
  Start pressed at once: device 2 ch, captured 2 ch, original 2 ch float, derived 16 kHz 16-bit 1 ch,
  SHA-256 of both downloads match, re-deriving from the downloaded original is byte-identical, browser
  played the file to its end, unsigned requests 403; 2 test objects deleted
  (docs/evidence/phase4/walkthrough_channels.txt).
- CI run 42652152398: all four jobs green; browser tests passed in Chromium and Microsoft Edge 156;
  backend 139 passed including the ffprobe check (docs/evidence/phase4/ci_run.txt).
- Open: test playback by ear; 60-second real sample through ffprobe; Edge on Windows; Wasabi encryption
  at rest NOT VERIFIED.
- Gate 4: conditions met; waiting for owner approval.

### Session 7 - 2026-11-09 - Option B: backend security testing

- Owner approved Gate 4 and asked for Option B (backend security testing: authentication, roles,
  permissions, APIs) from their test and optimisation list.
- New tests (28): `test_security_access.py` - every API route has a written access rule; every role
  plus an unassigned moderator against all 68 routes on its own project; on another project the
  answer equals the answer for a missing object; no response to a member contains the other project's
  IDs; request bodies cannot pull in another project's objects; CSRF on every state-changing route;
  malformed IDs; no credential fields in responses. `test_security_auth.py` - session fixation, hashed
  tokens, rights changes at the next request, single-use authenticator codes, throttled code and
  password guessing, identical sign-in failures, constant-cost unknown addresses, reset links ignore
  the Host header. `test_security_api.py` - size limits, NUL characters, injection strings,
  server-owned fields, errors echo nothing, protective headers on every kind of answer.
- Found and fixed: consent history readable by any moderator in the project, storage totals readable
  by every role (D-049); authenticator code replay and unthrottled password checks in a signed-in
  session (D-050, migration 0006); NUL characters caused server errors on every text input including
  sign-in, no request size limit, API answers cacheable (D-052); saving an unchanged language or
  retention list was a server error. Recorded the existing consent-capture rule (D-051). Each fix was
  removed once to watch its test fail, then restored.
- Results: backend 166 passed + 1 NOT RUN locally (ffprobe; runs in CI); frontend 50 passed; browser
  tests 2 passed in Chrome (docs/evidence/option_b/).
- Not covered: browser-side XSS and a web vulnerability scan (Phase 10).
- CI run 42660121140: all four jobs green; backend 167 passed (ffprobe included), browser tests
  passed in Chromium and Microsoft Edge 156, no known dependency vulnerabilities
  (docs/evidence/option_b/ci_run.txt).
- Option B done; waiting for the owner's next choice.

### Session 8 - 2026-11-09 - Option C: frontend testing

- Owner asked for Option C (frontend testing: forms, navigation, validation, error states).
- New tests (269): `src/app/pages.test.tsx` - every route (inventory read from routes.tsx) loaded
  with an axe check, loading, five kinds of failure with Try again, No access, signed-out redirect;
  `src/app/navigation.test.tsx` - the menu of each of the six roles, current-page marking, account,
  sign-out, no dead links; `src/app/forms.test.tsx` - every form (inventory counts `<form>` in the
  source): one request with the entered values, no second request while waiting, and validation,
  conflict, server and connection failures shown without losing what was typed. Shared fake backend
  `src/test/world.ts`; the fake fetch can now delay or drop a reply.
- Found and fixed: 17 of 19 error screens hid the server's reference and all used one generic title
  (D-053); validation errors never named the field (D-053); the New task page showed an empty project
  list when loading failed (D-053); the languages form wiped what was typed when saving failed; a task
  comment could be posted twice by a quick second click; the not-found page's link said "system
  status" but opened Projects. Each fix was removed once to watch its tests fail, then restored.
- Results: frontend 319 passed, build OK; browser tests 2 passed in Chrome
  (docs/evidence/option_c/). Backend unchanged since Option B.
- CI run 42665229942: all four jobs green; frontend 319 passed, browser tests passed in Chromium and
  Microsoft Edge 156, backend 167 passed, no known dependency vulnerabilities
  (docs/evidence/option_c/ci_run.txt).
- Option C done; waiting for the owner's next choice.

### Session 9 - 2026-11-09 - Option D: user journeys in a real browser

- Owner asked for Option D (browser automation of real user journeys, moderator recording first).
- New: `frontend/journeys/` (4 journeys, `playwright.journeys.config.ts`, `make journeys`) and a CI job
  "User journeys in a real browser" that starts PostgreSQL, SeaweedFS (S3) and the real backend, seeds
  one account per role, and runs the journeys in Chromium and Microsoft Edge.
- Journeys: (1) Super Admin creates a project, invites a moderator by email; the moderator sets a
  password from the email, starts the task, records consent and a face-to-face conversation and plays
  it back; both files download byte-identical through short-lived links; the audit log shows the
  steps. (2) The tab closes mid-recording; on return the moderator is told 0:05 was kept, keeps it, and
  the task is recorded. (3) Moderator, transcriber and client viewer are refused pages and records
  that are not theirs, by menu and typed address; after sign-out, Back shows sign-in. (4) Password
  reset by email; the old password fails and the other device's session ends.
- Results: all 4 passed twice in Google Chrome on the same database (reruns do not collide); server:
  0 errors; recordings 2-channel originals and 16 kHz mono delivery files; 8 test objects deleted from
  Wasabi (docs/evidence/option_d/journeys.txt). No product defects found by the journeys.
- Not covered by the screens yet: playing or downloading a recording as an administrator (the journey
  uses the API for downloads; exports arrive in Phase 9).
- CI run 42671870913: the secret scan flagged the fixed password the journeys gave their throwaway
  test accounts; the journeys now generate a random password per run (commit eedf3bd).
- CI run 42678318811 (commit 0d3b97f): all five jobs green; the 8 journeys passed in Chromium and
  Microsoft Edge 156; storage contract passed against SeaweedFS (docs/evidence/option_d/ci_run.txt).
  Two CI-only problems were fixed on the way: a test race in the reset journey (Edge typed into the
  sign-in page's Email field) and too-tight time limits for Edge's first start.

### Session 10 - 2026-11-10 - Option E: audio tests

- Owner asked for Options E, F, G and H, stopping if usage passes 90 %. Claude plan usage is not
  visible from here; machine use is watched instead (the disk was already at 97 % before the
  request, so the disk rule is "stop if free space drops below 1 GB").
- New: generated audio fixtures (`backend/tests/audio_fixtures.py`) and `test_audio_quality.py`
  (37 tests): level measurement against an independent calculation, silence and its threshold, low
  volume, exact clipping counts, over-range capture, every rate from 8 to 192 kHz, 1 to 8 channels, a
  10 ms recording, seven kinds of damaged file, impossible sample values, a part damaged in storage,
  and ffprobe on unusual formats (CI).
- Found and fixed (D-054): uploads with NaN or infinite samples were accepted; the WAV inspector
  crashed on a file cut inside its header or claiming zero channels, and accepted data that was not
  whole frames. Also fixed a test that failed when run across midnight UTC (it compared the storage
  folder with today's date instead of the recording's start date).
- Results: backend 204 passed + 4 NOT RUN locally (ffprobe; run in CI)
  (docs/evidence/option_e/make_check_backend.txt).

### Session 10 (continued) - Option F: storage tests

- New: `backend/tests/test_storage_contract.py`, one contract run against a fake S3 on every run,
  against the real Wasabi bucket from this machine (folder `dev-aws-dev/contract/`, emptied after),
  and against SeaweedFS in the CI journeys job.
- Results: 16 passed on fake S3 and Wasabi (links expire after 3 s; unsigned and altered links get
  403); 0 objects left. No defects found.
- Wasabi does not report encryption at rest through its API (no `ServerSideEncryption` on objects,
  empty bucket encryption setting): still NOT VERIFIED; needs Wasabi's written statement or an account
  setting check by the owner.

### Session 10 (continued) - Option G: load test

- New: `backend/loadtest/f2f_load.py` (linted and type-checked with the backend): 50 moderators
  recording at once at real-time pace plus 10 people browsing; per-endpoint latency, errors, delay
  to files ready, CPU, memory, database connections; stops itself above 90 % CPU (5-second average)
  or memory, the owner's rule.
- 1 server process: 2 059 requests, 0 errors, 576 MB uploaded, 50/50 recordings ready (median 7.6 s,
  max 15.1 s after stop), CPU 5-second peak 83 %, memory 47 %, 16 database connections; slowest
  answers 3-9 s during the start and completion bursts.
- 4 server processes: stopped by the 90 % rule after 16 s (CPU 95 % while 50 people signed in at
  once; one Argon2id check takes about 150 ms on all 4 cores), 0 errors before the stop.
- Not a capacity proof (CAP-004): load generator, database and server shared one 4-CPU machine; no
  Redis worker. 210 test objects (1.36 GB) deleted from Wasabi (docs/evidence/option_g/).

### Session 10 (continued) - Option H: recovery tests

- New: `backend/tests/test_recovery.py` (9 tests), journey `frontend/journeys/network.spec.ts`
  (connection off for 8 s mid-recording), scripted database restart and outage against the running
  backend.
- Found and fixed (D-055): a recording could stay PROCESSING forever after a worker stopped (the
  re-delivered job refused it) and UPLOADED forever after a failed queue hand-off; now claimed
  atomically, swept at start-up and every minute, and recoverable with
  `python -m app.cli recover-recordings`; storage and database outages answered as 503
  `STORAGE_UNAVAILABLE` / `DATABASE_UNAVAILABLE` with Retry-After instead of internal errors;
  `python -m app.cli retention` was listed but did nothing (now runs). Each recovery fix was removed
  once to watch its tests fail (7 of 8 failed; the restart test passes either way, by design).
- Results: database restart transparent (session kept); outage answered 503, no error-level log; all
  5 journeys passed in Chrome; 8 test objects deleted from Wasabi (docs/evidence/option_h/).
- CI run 42681849714 (commit a42e1f0, Options E-H): all five jobs green; backend 225 passed (ffprobe
  included), frontend 319, browser tests 4, journeys 10 (5 in Chromium, 5 in Edge), storage contract
  against SeaweedFS 8 passed; no known dependency vulnerabilities (docs/evidence/option_h/ci_run.txt).
- Options E, F, G and H done; waiting for the owner's next choice.

### Session 11 - 2026-11-10 - Optimisation items O1-O12

- Owner asked to complete the optimisation list.
- O1 uploads (D-060): a session ended mid-recording pauses sending instead of losing the rest;
  Retry-After honoured; retries spread. O2 background processing and O6 Redis job queues: already in
  place since Phase 4 (D-043), now covered by the recovery tests and the container job. O3 large files
  and O4 checksums (D-056): one copy on disk, block-wise conversion, 16 MB transfer parts, size and
  SHA-256 checked after both uploads, `verify-assets`. O5 database (D-057): 3 fewer queries on every
  request, per-row query removed from the moderator's participant list, project details loaded only
  when read, four indexes (migration 0007; busy project's audit page 20.5 ms -> 0.14 ms). O7 lists:
  every list endpoint paged or explained; task search by code. O8 monitoring: query count and time on
  every request log line, slow request and slow query warnings, storage in readiness. O9 backups
  (D-058): backup and restore scripts, pruning; CI backs up, deletes, restores. O10 capacity (D-059):
  process and pool counts from configuration; staff-account limit enforced. O11 frontend (D-061):
  pages load on first visit (first screen 107 KB, was 120 KB), compression and caching, bundle budget;
  fixed the web server's content policy, which would have blocked recording playback from Wasabi.
  O12 lifecycle (D-056): orphaned files and leftover scratch folders cleaned.
- Results: backend 239 passed + 13 NOT RUN locally (4 ffprobe, 9 live storage: ran on Wasabi
  separately); frontend 323; browser tests 2; journeys 6/6 in Chrome; storage contract 9/9 on Wasabi
  (docs/evidence/option_o/). Test objects deleted from Wasabi. The development database's
  staff-account limit was raised to 1000 in Settings because it holds the 150 load-test accounts.

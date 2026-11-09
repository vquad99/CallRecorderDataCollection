# Decisions

Status words: Accepted (in force), Proposed (needs owner approval), Open (blocker or question).
The owner approved Phase 0 on 2026-11-09; the decisions proposed in it are Accepted.

## Decisions

| ID | Date | Status | Decision | Reason |
|---|---|---|---|---|
| D-001 | 2026-11-09 | Accepted | Standalone repository `/home/quad99/conversation-collection-platform`, unrelated to any other project on the machine. | Owner: "this is totally different project". |
| D-002 | 2026-11-09 | Accepted (Phase 0 approval) | Modular monolith on the runbook B4 stack (React + TS, FastAPI, PostgreSQL + Alembic, Celery + Redis, FFmpeg, S3-compatible storage, Docker, Nginx). | Repository is empty, so no existing equivalent to keep (runbook B4). |
| D-003 | 2026-11-09 | Accepted (Phase 0 approval) | Face-to-face capture through an AudioWorklet writing raw 32-bit float PCM; MediaRecorder not used. | MediaRecorder's usual output (Opus/WebM) is lossy. |
| D-004 | 2026-11-09 | Accepted (Phase 0 approval) | Browser echo cancellation, noise suppression and auto gain requested off; applied settings stored per session. | Browsers enable these by default; delivered audio must be unprocessed. |
| D-005 | 2026-11-09 | Accepted (Phase 0 approval) | Recovery by uploading ~5-second chunks during recording; no audio written to browser storage. | Meets both spec ("no private audio in shared browser storage by default") and runbook G2.11 ("preserve recoverable data where safely possible"). |
| D-006 | 2026-11-09 | Accepted (Phase 0 approval) | Derived 16 kHz file produced server-side by FFmpeg (`soxr` resampler), parameters recorded, labelled derived. | Spec 4.2, runbook G3; see B-03. |
| D-007 | 2026-11-09 | Open | Telephony channel separation method (T1 multi-track, T2 per-leg, T3 live streams) chosen at Gate 5 from evidence. | Provider-dependent (ARCHITECTURE.md section 6). |
| D-008 | 2026-11-09 | Accepted (Phase 0 approval) | Moderator joins through the provider's browser client: 100 phone legs at 50 conferences (150 if a phone leg is needed). | Spec 10. |
| D-009 | 2026-11-09 | Accepted (Phase 0 approval) | Server-side sessions, HttpOnly cookie + CSRF token; no tokens in localStorage. | AUTH-013, PWA-007. |
| D-010 | 2026-11-09 | Accepted (Phase 0 approval) | Only Super Admin creates users and projects; Project Admin manages its own projects and assigns existing users. | Sources say Project Admin "manages assigned projects"; creation rights not stated. |
| D-011 | 2026-11-09 | Accepted (Phase 0 approval) | Capacity targets in `system_settings`; per-project targets on projects; editable in the admin UI. | CAP-001/002. |
| D-012 | 2026-11-09 | Accepted, amended by D-020 | Local S3-compatible storage in Docker; Wasabi bucket in cloud (D-019). | Same S3 API in both. |
| D-013 | 2026-11-09 | Accepted | Phase 0 document set = runbook C0.2 list; first-pass `TRACEABILITY.md` renamed `REQUIREMENT_TRACEABILITY.md`; runbook copied verbatim to `docs/RUNBOOK_SOURCE.md`. | Runbook supersedes the spec's shorter list. |
| D-014 | 2026-11-09 | Accepted | Status vocabulary = runbook A3 (`NOT STARTED` ... `ACCEPTED`). | Spec 13 and runbook A3 differ; the spec's own initial "Blocked pending provider proof" is not in its list. |
| D-015 | 2026-11-09 | Accepted (Phase 0 approval) | One membership table `project_memberships` (spec: user_project_memberships); one asset table `audio_assets` (runbook I1: recording_assets). | Same concept, one table each; avoids duplicate sources of truth. |
| D-016 | 2026-11-09 | Accepted | Spec v1.0 and runbook both binding; runbook prefixes FTF, AQC, OPS used; extra prefixes for rules the runbook does not prefix. | Owner supplied the runbook after the spec. |
| D-019 | 2026-11-09 | Accepted | Cloud object storage = Wasabi (S3-compatible). Bucket `callrec57`, region `ap-southeast-1` (Singapore). Access key checked 2026-11-09: read-only bucket listing returned 200, bucket empty. Key kept on the build machine at `~/.config/ccp/wasabi_credentials.csv` (mode 600, outside the repository, never committed); the key file has no user name, so it may be the account's main key - a key limited to this bucket is preferred (SEC-014). used only through the storage adapter (STOR-012). To check against Wasabi's official documentation before Phase 4, all NOT VERIFIED: private buckets and public-access blocking, pre-signed URL support and expiry, encryption at rest, versioning, lifecycle/expiry rules, multipart upload, minimum storage-duration billing (affects deletion and temporary export bundles), download/egress terms, available regions (data residency). | Owner: "lets use wasabi buckets". |
| D-020 | 2026-11-09 | Accepted | Local S3 stand-in = SeaweedFS 4.51 (`chrislusf/seaweedfs:4.51`) instead of MinIO. | MinIO's Docker Hub repository returns 404 and its Quay repository lists no active tags (checked 2026-11-09), so MinIO cannot be pinned. |
| D-021 | 2026-11-09 | Accepted | Backend tests live in `backend/tests/`, outside the `app` package. | Runbook D1 shows `app/tests/` as "a structure similar to"; keeping tests outside the package keeps test code out of the production image (GEN-002). |
| D-022 | 2026-11-09 | Accepted | ESLint 9.39.5 (marked unsupported upstream) with eslint-plugin-jsx-a11y 6.10.2. | The accessibility plugin rejects ESLint 10 (npm peer conflict). Revisit when it supports ESLint 10. |
| D-023 | 2026-11-09 | Accepted | Dependencies resolved only from releases at least two weeks old (uv `exclude-newer = 2026-10-26`, `npm install --before=2026-10-26`); exact versions in lockfiles and TECH_STACK.md. | Stable, reproducible builds (ARCH-003). |
| D-024 | 2026-11-09 | Accepted | Baseline migration 0001 creates `system_settings`; its `updated_by` foreign key to `users` is added by the Phase 2 migration. | Phase 1 needs one real migration to prove the migration path; the users table belongs to Phase 2. |
| D-025 | 2026-11-09 | Accepted | FND-027 (development-only demo-account seed) moves to Phase 2. | Demo accounts need the users table; a seed command with nothing to seed would be a stub (GEN-002). |
| D-026 | 2026-11-09 | Accepted | Container start-up, health checks and restart persistence (TM-FND-02) are tested by the CI `compose` job. | The build machine has no Docker (B-08). |
| D-027 | 2026-11-09 | Accepted | Login throttling counts failures in PostgreSQL (`login_attempts`): 5 per account and 20 per IP in 15 minutes by default, all configurable. | Works without Redis in development and tests; volume is small (50 staff). SECURITY.md first said Redis. |
| D-028 | 2026-11-09 | Accepted | A user can hold several roles (`user_roles`); `project_memberships` links a user to a project without its own role. | Runbook E3 treats "assign role" and "assign project membership" as separate actions. |
| D-029 | 2026-11-09 | Accepted | Code permission list made to follow the approved matrix exactly: Super Admin does not hold `calls.start` or `recordings.create`; Client Viewer holds `participants.view`. A test reads the matrix in ARCHITECTURE.md and fails on any difference. | The approved matrix is the source. Phase 3 must return participant IDs only (no names or phone numbers) to Client Viewers. |
| D-030 | 2026-11-09 | Accepted | Demo accounts use `@example.org` (reserved for documentation, RFC 2606). | The email checker rejects `.test` addresses, so seeded `.test` accounts could not be edited in the admin screen. |
| D-031 | 2026-11-09 | Accepted | The 100-character line limit is not applied to test files. | Test files hold long API paths and request bodies; production code keeps the limit. |
| D-032 | 2026-11-09 | Accepted | `GET /api/v1/projects/{id}/member-candidates` (needs `projects.members`) lists active non-members for the team picker. | A Project Admin must add people without the Super-Admin-only user list. |
| D-033 | 2026-11-09 | Accepted | A request about a project the caller is not a member of answers 404, before any finer permission check. | Does not reveal which projects exist. |
| D-034 | 2026-11-09 | Accepted | Email: `file` backend (writes .eml files) for development and tests; production refuses to start unless `EMAIL_BACKEND=smtp` and `SMTP_HOST` are set. | Invitations and password resets must really be sent in production; see B-13. |
| D-018 | 2026-11-09 | Accepted | AI transcription uses Deepgram through the ASR adapter and is optional: on/off per project, default off; off = human transcription from an empty transcript. Replaces the spec's initial candidates (Whisper Large-v3, AI4Bharat). | Owner: "transcription we can use deepgram and make it optional". Deepgram's models, language coverage, pricing and data handling are NOT VERIFIED until checked in Phase 7 (docs/integrations/deepgram/). |
| D-017 | 2026-11-09 | Accepted (Phase 0 approval) | Raw provider payloads and raw ASR responses stored in private object storage, referenced from the database; fields the workflow reads get typed columns. | Keeps the database queryable; runbook I4.2 and J2 require keeping raw data. |

## Open blockers and questions

| ID | Blocks | Question / blocker | Needed from |
|---|---|---|---|
| B-01 | Phase 5-6; 38 TEL requirements | No telephony provider shortlist, no test credentials. | Owner: shortlist (>= 2) or permission to research; then test credentials |
| B-02 | AUDIO-002/013 acceptance | If the provider gives 8 kHz phone audio, the 16 kHz telephony WAV is an up-sampled copy. Acceptable, with that stated in its processing history? | Client |
| B-03 | AUDIO-014/015 acceptance | Browser mics run at 44.1/48 kHz; 16 kHz needs a resample, which is not lossless. Accept a documented resample with the original kept? | Client |
| B-04 | Phase 5, 10 | Hosting provider and account; region for data residency. Storage resolved: Wasabi `callrec57` in Singapore (D-019) - client must confirm data may be stored outside India. | Owner / client |
| B-05 | Storage sizing, deletion workflow | Retention period for final files, browser originals (6x the size of the derived file) and provider originals. | Client |
| B-06 | Phase 7 | Launch languages and dialects; reference audio with human transcripts for evaluation. | Client |
| B-07 | Phase 7 | Deepgram account and API key (server-side secret); confirm Deepgram covers the launch languages/dialects; confirm sending participant audio to Deepgram is allowed by the client and the consent text. No GPU needed any more (D-018). | Owner / client |
| B-08 | Local container runs | Build machine (aws-dev) has no Docker or FFmpeg and about 2 GB free disk. Phase 1 worked around it (private PostgreSQL for tests, CI runs the containers - D-026). FFmpeg is needed on this machine from Phase 4. | Owner: install Docker + FFmpeg and free disk, when convenient |
| B-09 | Phase 4 device tests, Phase 10 | Domain name + TLS (microphone needs HTTPS outside localhost). | Owner |
| B-10 | TEL-015, PART-006 | Call-recording consent law and provider terms in India; consent script wording. NOT VERIFIED. | Owner / legal |
| B-11 | - | Resolved 2026-11-09: pushes use a deploy key with write access on github.com/vquad99/CallRecorderDataCollection; CI = GitHub Actions. | - |
| B-13 | Production email | SMTP provider, sender address and credentials for invitations and password resets (D-034). | Owner |
| B-12 | Traceability to source text | The spec v1.0 was pasted in chat and is not saved as a file in the repository (the runbook is, as RUNBOOK_SOURCE.md). | Owner: the spec file, if it should be kept verbatim |

## Provider documentation log (GEN-005)

| Provider | Claim | Source URL | Access date | Result |
|---|---|---|---|---|
| - | No provider documentation checked yet | - | - | NOT VERIFIED |

# Claude Code: Step-by-Step Implementation Runbook
## Conversation Collection Platform — complete build instructions

**Purpose:** This is the execution manual for implementing the platform in the existing repository. It expands the product specification into small coding tasks, verification commands, acceptance gates, and mandatory reporting rules.

**Primary instruction to Claude Code:** Work in small, testable increments. Never skip a requirement. Never claim a feature works without running the test that proves it.

---

# PART A — Rules Claude must obey

## A1. Work rules

1. Read this entire runbook before changing code.
2. Inspect the repository before choosing or changing frameworks.
3. Preserve existing working code. Do not delete or rewrite it without explaining the reason and obtaining approval.
4. Create a requirement ID for every requirement. Keep the ID in the tracker, relevant code comments where useful, and tests.
5. Implement one small task at a time.
6. After each task: format, lint, type-check, test, inspect the diff, and update the tracker.
7. Do not move to the next phase while the current phase's gate is failing.
8. Do not use fake data or mocked success in production paths. Mocks are allowed only in clearly isolated tests.
9. Do not create buttons that do nothing.
10. Do not leave `TODO`, `FIXME`, placeholder pages, stub methods, or `NotImplemented` in a feature marked complete.
11. If an external service is not configured, show a truthful `Not configured` state. Never pretend it succeeded.
12. Do not invent telephony endpoints, provider features, prices, compliance permissions, audio formats, or model capabilities.
13. Use official provider documentation. Save the URL, access date, relevant feature, and test evidence in `docs/integrations/`.
14. If a test cannot be run, mark it `NOT RUN`, explain why, and do not mark the requirement verified.
15. If the context window or time is running out, save the current state, update the tracker, and stop at a clean checkpoint.

## A2. Required response after every coding session

Claude must report exactly:

- Phase and task completed:
- Requirement IDs addressed:
- Files created:
- Files changed:
- Database migrations:
- API routes:
- UI routes/components:
- Tests run (exact commands):
- Test results (passed/failed/skipped):
- Manual checks performed:
- Known defects:
- Blockers:
- Tracker updated:
- Git commit:
- Next single task:

Do not use phrases such as “fully done” unless the relevant acceptance gate has passed.

## A3. Status vocabulary

Use only these statuses:

- `NOT STARTED`
- `IN PROGRESS`
- `BLOCKED`
- `IMPLEMENTED — TESTS FAILING`
- `IMPLEMENTED — AUTOMATED TESTS PASS`
- `VERIFIED`
- `ACCEPTED`

`VERIFIED` requires automated tests and manual verification. `ACCEPTED` requires the phase gate to be approved.

---

# PART B — Product contract

## B1. Product

Build one cloud-hosted responsive web application that can be installed as a Progressive Web App (PWA). There is no native Android or iOS application.

The platform has two recording modes:

### Telephony mode

1. Moderator starts an outbound call from the web portal.
2. The provider calls Participant A.
3. The moderator adds Participant B to the same conference.
4. Moderator explains the project and obtains consent.
5. Moderator leaves the conference.
6. A and B continue talking.
7. Recording continues after moderator departure.
8. The final audio must keep A and B on separate channels.
9. Store one stereo WAV: A on left, B on right, 16 kHz, 16-bit signed PCM.
10. Preserve original provider recording assets and record all derived-file operations.

**Critical:** A mixed mono call recording cannot be converted into genuine separate participant channels by copying it to left and right. If the provider cannot provide independent participant tracks or dual-channel recording with verified channel mapping, mark this requirement BLOCKED. Do not fake it.

Telephone networks may encode/compress audio before the provider records it. A PCM WAV export does not prove that the telephone call was uncompressed end-to-end. Record the actual codec and provider recording specifications. Do not make unsupported “uncompressed end-to-end” claims.

### Face-to-face mode

1. Moderator opens the web application on a computer.
2. Moderator selects a microphone and checks input level.
3. Two participants sit near the fixed microphone and speak.
4. Browser captures the microphone stream.
5. Preserve the original browser capture.
6. Create a derived WAV target: mono, 16 kHz, 16-bit signed PCM.
7. Keep face-to-face assets in a separate folder/prefix from telephony assets.

If browser capture is not already PCM WAV, any conversion is a derived asset. Never describe converted audio as untouched original capture.

## B2. Initial capacity settings

Store these as editable configuration, not source-code constants:

| Setting | Initial value |
|---|---:|
| Staff accounts | 50 |
| Concurrent telephony conferences | 50 |
| Participants in final conversation | 2 |
| Total recording hours/day | 250 |
| Face-to-face hours/day | 125 |
| Telephony hours/day | 125 |
| Hosting | Cloud |
| Interface | Web + installable PWA |

Capacity is not proven until a load test and provider-side concurrency confirmation pass.

## B3. Roles

- Super Admin
- Project Admin
- Moderator
- Transcriber
- QC Executive
- Client Viewer

All authorization must be enforced on the backend, not only by hiding frontend controls.

## B4. Technology baseline

Use this stack unless the repository already has a functioning equivalent:

- Frontend: React + TypeScript
- Backend: Python + FastAPI
- Database: PostgreSQL
- Migrations: Alembic
- Background jobs: Celery + Redis
- Audio inspection/conversion: FFmpeg plus a tested Python audio library
- Object storage: private S3-compatible storage
- Deployment: Docker
- Reverse proxy: Nginx or managed cloud ingress
- PWA: web manifest + service worker
- Tests: Pytest for backend; Vitest/React Testing Library for frontend; Playwright for end-to-end tests

Pin versions. Record the versions in `docs/TECH_STACK.md`.

---

# PART C — Phase 0: Inspect and plan

## C0.1 Inspect the repository

Run and record:

```bash
pwd
ls -la
find . -maxdepth 2 -type f | sort | head -300
git status --short
git log -5 --oneline
```

Inspect:
- package manifests
- Python dependency files
- Docker files
- environment examples
- migrations
- test folders
- CI configuration
- deployment configuration

Do not print secret values. It is acceptable to list environment variable names, but redact values.

## C0.2 Create project documentation

Create:

```text
docs/
  REQUIREMENTS.md
  REQUIREMENT_TRACEABILITY.md
  ARCHITECTURE.md
  DATABASE.md
  API_CONTRACT.md
  SECURITY.md
  AUDIO_SPECIFICATION.md
  TELEPHONY_PROVIDER_EVALUATION.md
  TEST_PLAN.md
  BUILD_STATUS.md
  DECISIONS.md
  TECH_STACK.md
  DEPLOYMENT.md
  integrations/
  evidence/
```

## C0.3 Build the requirement traceability table

Give every requirement a unique ID. Suggested prefixes:

- `AUTH-###` authentication
- `USER-###` users and roles
- `PROJ-###` projects
- `PART-###` participants
- `TASK-###` task workflow
- `TEL-###` telephony
- `FTF-###` face-to-face recording
- `STOR-###` storage
- `AQC-###` audio quality control
- `ASR-###` AI transcription
- `TRN-###` human transcription
- `TQC-###` transcript quality control
- `EXP-###` exports
- `DASH-###` dashboards
- `SEC-###` security and audit
- `PWA-###` PWA
- `OPS-###` deployment and operations

Each row must contain:
`ID | requirement | phase | database | API | UI | test | status | evidence`

## C0.4 Phase 0 gate

Do not code application features until:
- Existing repository is understood.
- Requirements are mapped.
- Architecture is documented.
- Unknowns are listed.
- No existing code is deleted.
- Build tracker contains all modules.

Ask the owner to approve major architectural changes before making them.

---

# PART D — Phase 1: Foundation

## D1. Create the backend foundation

Create a structure similar to:

```text
backend/
  app/
    main.py
    core/
      config.py
      logging.py
      security.py
      errors.py
    api/
      router.py
    db/
      base.py
      session.py
      migrations/
    modules/
    tests/
  pyproject.toml
  Dockerfile
```

Tasks:
1. Create FastAPI application factory.
2. Load configuration from environment variables.
3. Validate required environment variables at startup.
4. Add structured JSON logging.
5. Add request ID middleware.
6. Add global exception handlers.
7. Add `/health/live` and `/health/ready`.
8. Configure PostgreSQL connection pool.
9. Configure Alembic.
10. Add test database configuration.
11. Add CORS allowlist from environment variables.
12. Add API version prefix such as `/api/v1`.

Verification:
- Backend starts from a clean checkout.
- `/health/live` returns success.
- `/health/ready` fails clearly if the database is unavailable.
- Invalid configuration prevents unsafe startup.
- Logs contain request IDs but no secrets.

## D2. Create the frontend foundation

Suggested structure:

```text
frontend/
  src/
    app/
    api/
    auth/
    components/
    features/
    layouts/
    routes/
    styles/
    test/
  public/
  package.json
  vite.config.ts
  tsconfig.json
```

Tasks:
1. Create React + TypeScript application.
2. Configure strict TypeScript.
3. Configure route handling.
4. Create shared API client.
5. Add global error boundary.
6. Add loading, empty and error components.
7. Add accessible form controls.
8. Add responsive application shell.
9. Add frontend unit test setup.
10. Add lint and format commands.

Verification:
- Frontend starts.
- Type check passes.
- Lint passes.
- Unit test runner passes.
- Browser console has no application errors.

## D3. Database and local environment

Tasks:
1. Create Docker Compose for app, database, Redis and local object storage.
2. Add health checks.
3. Add persistent local development volumes.
4. Add `.env.example` with names and safe example values only.
5. Add `.gitignore`.
6. Add database migration command.
7. Add seed command for development-only demo accounts.
8. Ensure demo accounts cannot be seeded in production.

Verification:
- One documented command starts dependencies.
- Migration runs from an empty database.
- Restart preserves database data.
- No secrets appear in Git.

## D4. Phase 1 gate

Required:
- Clean setup documented.
- Backend and frontend start.
- Database migration works.
- Health checks work.
- Lint, type check and tests pass.
- CI runs the same checks.

---

# PART E — Phase 2: Authentication, users, roles and projects

## E1. Authentication

Database:
- `users`
- `sessions` or equivalent session storage
- `password_reset_tokens`
- `roles`
- `permissions`
- `role_permissions`

Tasks:
1. Create user model with normalized unique email/username.
2. Hash passwords with a modern password hashing algorithm.
3. Implement login endpoint.
4. Implement logout and session revocation.
5. Implement password reset with expiring single-use tokens.
6. Add login throttling.
7. Add account active/disabled state.
8. Add session expiry.
9. Add secure, HTTP-only, SameSite cookies or a documented secure token strategy.
10. Never put long-lived secrets in browser local storage.
11. Add audit events for login failures, password changes and account disablement.
12. Add optional MFA only after the base flow is secure.

API examples:
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/password/forgot`
- `POST /api/v1/auth/password/reset`

Frontend:
- Login page.
- Forgot password page.
- Reset password page.
- Session-expired message.
- Protected route wrapper.

Tests:
- Valid login succeeds.
- Invalid password fails.
- Disabled user fails.
- Expired session fails.
- Logout revokes session.
- Rate limit blocks repeated failures.
- Password reset token cannot be reused.
- Password is never returned by an API.

## E2. Role-based access control

Tasks:
1. Define role and permission constants centrally.
2. Create backend permission dependency.
3. Apply permissions to every protected API.
4. Add project membership checks.
5. Add frontend route and navigation filtering for usability only.
6. Keep backend checks authoritative.
7. Add tests that call APIs directly with each role.

Permission examples:
- `users.manage`
- `projects.manage`
- `tasks.assign`
- `calls.start`
- `recordings.view`
- `recordings.download`
- `transcripts.edit`
- `transcripts.review`
- `exports.create`
- `audit.view`

Tests:
- Moderator cannot call user-management API.
- Transcriber cannot download an unassigned recording.
- QC Executive can access assigned QC items only.
- Client Viewer is read-only.
- Changing frontend route manually does not bypass permissions.

## E3. User management

Tasks:
1. Build user list with pagination and search.
2. Build create/edit user form.
3. Assign role.
4. Assign project membership.
5. Activate/deactivate account.
6. Add CSV import with validation preview.
7. Add CSV export with permission checks.
8. Audit all role and membership changes.

## E4. Project management

Database:
- `projects`
- `project_languages`
- `project_memberships`
- `project_audio_rules`
- `project_transcription_guidelines`
- `project_retention_rules`

Tasks:
1. Create project CRUD.
2. Add project code uniqueness.
3. Add languages and dialects.
4. Add allowed recording modes.
5. Add daily recording targets.
6. Add audio specification fields.
7. Add transcription guideline version.
8. Add retention policy.
9. Add project lifecycle status.
10. Prevent archived projects from receiving new work.

Frontend:
- Project list.
- Project create/edit.
- Project details tabs: overview, team, audio rules, language, retention.

Tests:
- CRUD.
- Duplicate project code rejected.
- Project isolation enforced.
- Archived project task creation blocked.

## E5. Phase 2 gate

No placeholder login. No frontend-only permissions. Every role must be tested against protected APIs.

---

# PART F — Phase 3: Participants, task assignment and workflow

## F1. Participant management

Database:
- `participants`
- `participant_project_links`
- `consent_records`

Tasks:
1. Create participant ID generator.
2. Store only necessary participant details.
3. Normalize phone numbers to a consistent format.
4. Add duplicate detection.
5. Restrict phone-number visibility by permission.
6. Store consent separately from participant profile.
7. Record consent method, time, staff member and policy/version.
8. Add participant correction workflow.
9. Add retention and deletion support.

Tests:
- Duplicate detection.
- Phone masking.
- Consent audit history.
- Unauthorized export denied.

## F2. Task assignment

Database:
- `tasks`
- `task_assignments`
- `task_status_history`
- `task_comments`

Tasks:
1. Define allowed task statuses.
2. Define allowed state transitions in one backend service.
3. Create task with project, mode, participant A, participant B and target date.
4. Assign moderator.
5. Add priority and due date.
6. Add reassignment with reason.
7. Add task comments.
8. Add task list filters.
9. Add task detail page.
10. Add task history timeline.
11. Reject invalid state transitions at API level.
12. Use database transactions for state changes and history creation.

Suggested lifecycle:

```text
DRAFT
  -> ASSIGNED
  -> IN_PROGRESS
  -> RECORDED
  -> AUDIO_QC
  -> TRANSCRIPTION_PENDING
  -> TRANSCRIPTION_IN_PROGRESS
  -> TRANSCRIPT_QC
  -> APPROVED
```

Additional terminal or exception states:
`REJECTED`, `RETURNED`, `CANCELLED`, `ON_HOLD`.

Do not allow arbitrary state jumps.

Tests:
- Valid transitions succeed.
- Invalid transitions fail.
- Assignment is project-scoped.
- Reassignment creates history.
- Only assigned moderator can start the task.

## F3. Phase 3 gate

A task must be traceable from creation to assignment. Participant data and consent are permission-protected. Invalid transitions fail in direct API tests.

---

# PART G — Phase 4: Storage and face-to-face browser recording

## G1. Object storage

Tasks:
1. Create storage abstraction interface.
2. Implement private S3-compatible bucket.
3. Configure server-side encryption.
4. Use short-lived signed URLs.
5. Add multipart/resumable uploads.
6. Verify upload completion.
7. Calculate SHA-256 checksum.
8. Compare source and stored checksum.
9. Save asset metadata in database.
10. Link original and derived assets.
11. Add retention and deletion jobs.
12. Add storage usage reporting.

Suggested object keys:

```text
project-code/face-to-face/YYYY/MM/DD/task-id/original/
project-code/face-to-face/YYYY/MM/DD/task-id/derived/
project-code/telephony/YYYY/MM/DD/task-id/provider-original/
project-code/telephony/YYYY/MM/DD/task-id/final/
project-code/transcripts/task-id/
```

Never expose bucket publicly.

## G2. Face-to-face recording UI

Tasks:
1. Check browser support.
2. Request microphone permission after user action.
3. Enumerate microphones after permission.
4. Let moderator select a device.
5. Show live input-level meter.
6. Add a short test recording and playback.
7. Display project audio rules before start.
8. Add start and stop controls.
9. Display recording duration and state.
10. Capture interruption/error events.
11. Preserve local recoverable data where safely possible.
12. Upload using resumable upload.
13. Show upload progress and retry.
14. Do not claim recording continues after tab closure or device sleep.
15. Store browser capture as original asset.

## G3. Audio conversion and validation

Use a deterministic, tested processing pipeline.

Target derived face-to-face WAV:
- Mono.
- 16,000 samples/second.
- 16-bit signed integer PCM.
- WAV container.

Tasks:
1. Inspect actual original file.
2. Decode source without noise reduction or enhancement.
3. Resample to 16 kHz using a documented high-quality resampler.
4. Convert to mono only when source channel handling is understood.
5. Convert sample representation to signed 16-bit PCM.
6. Write derived WAV.
7. Inspect output independently using FFprobe or equivalent.
8. Store processing tool/version/parameters.
9. Calculate checksum.
10. Never overwrite original capture.

Important: downmixing stereo to mono can change audio. Document the exact method. Do not apply noise suppression, normalization, compression, EQ or enhancement.

## G4. Phase 4 gate

- Browser recording works in supported browsers.
- Permission denial is handled.
- Original file is retained.
- Derived WAV passes independent format inspection.
- Hash and metadata are stored.
- Upload recovery works.
- Unauthorized download fails.

---

# PART H — Phase 5: Telephony proof of capability

**Do this before building the full telephony user interface.** This is an external dependency and a high-risk requirement.

## H1. Provider research

Evaluate at least two providers. Use official technical documentation and written provider answers.

Create a comparison table for:
- India outbound calling.
- API call creation.
- Conference creation.
- Add participant to active conference.
- Moderator departure without ending conference.
- Recording continues after moderator leaves.
- Separate participant tracks or verified dual-channel recording.
- Recording retrieval API.
- Webhooks and signatures.
- 50 concurrent conferences.
- Call-leg limits.
- Supported recording format/sample rate.
- Retention and storage.
- Per-minute cost and fixed charges.
- Contract and compliance requirements.

Do not select a provider based only on a cheap advertised plan.

## H2. Provider proof-of-concept

Build a small isolated proof-of-concept, not the complete production module.

Tasks:
1. Store provider credentials in server-side environment/secret manager.
2. Implement provider adapter interface.
3. Create one outbound call to A.
4. Add B to the same conference.
5. Join moderator.
6. Obtain consent.
7. Start recording at the correct point.
8. Have moderator leave.
9. Confirm A and B remain connected.
10. Confirm recording continues.
11. End participant call.
12. Receive webhook.
13. Download provider recording.
14. Inspect provider's raw recording.
15. Identify whether the provider gives separate tracks or only a mix.
16. If separate tracks exist, map A and B using a controlled test.
17. Combine independent tracks into stereo without altering content.
18. Validate left and right independently.
19. Save test call IDs, provider event IDs and files as non-sensitive evidence.
20. Get written confirmation of 50-conference capacity.

## H3. Audio acceptance test

Speak a different test phrase on each participant line:
- A says: “This is participant A.”
- B says: “This is participant B.”

Inspect:
- Left channel alone.
- Right channel alone.
- Both channels together.
- Cross-channel leakage.
- Alignment.
- Duration.
- Sample rate.
- Bit depth.
- PCM codec.
- Moderator audio presence/absence according to agreed policy.

If the provider only returns a mixed track, fail the test. Never duplicate the mixed file into two channels.

## H4. Phase 5 gate

The provider is not accepted until every critical item has evidence. If it fails, keep telephony status `BLOCKED` and present provider alternatives. Continue unrelated platform modules, but do not build a fake integration.

---

# PART I — Phase 6: Full telephony module

## I1. Backend domain model

Create:
- `provider_accounts`
- `call_sessions`
- `call_participants`
- `call_events`
- `provider_webhook_events`
- `recording_assets`

Store:
- Internal task ID.
- Provider call ID.
- Conference ID.
- Participant role (A, B, moderator).
- Call state.
- Start/end timestamps.
- Consent status.
- Recording state.
- Provider event IDs.
- Failure code and safe diagnostic details.

## I2. Provider adapter

Define a stable interface such as:

```python
class TelephonyProvider:
    async def start_call_to_a(self, request): ...
    async def add_b_to_conference(self, conference_id, participant): ...
    async def join_moderator(self, conference_id, moderator): ...
    async def start_recording(self, conference_id): ...
    async def moderator_leave(self, conference_id, moderator_id): ...
    async def end_conference(self, conference_id): ...
    async def get_recording(self, provider_recording_id): ...
    async def verify_webhook(self, headers, body): ...
```

These are internal interface names, not provider API endpoints. Implement actual calls only from verified official provider documentation.

## I3. Call state machine

Implement server-side states, for example:

```text
CREATED
CALLING_A
A_CONNECTED
ADDING_B
B_CONNECTED
MODERATOR_CONNECTED
CONSENT_PENDING
CONSENT_CONFIRMED
RECORDING
MODERATOR_LEFT
PARTICIPANTS_CONTINUING
COMPLETED
FAILED
CANCELLED
```

Rules:
- Do not record participant conversation before required consent.
- If A or B refuses consent, end or cancel according to project policy.
- Moderator departure must not end the conference.
- Only authorized action can end the participant conference.
- Webhook events may arrive late or more than once.
- Invalid state transitions must fail safely.

## I4. Webhooks

Tasks:
1. Verify provider signature.
2. Store raw event metadata safely.
3. Add unique constraint on provider event ID.
4. Make processing idempotent.
5. Acknowledge quickly and process heavy work asynchronously.
6. Retry transient failures.
7. Send permanently failed events to a dead-letter queue.
8. Provide admin webhook event viewer.
9. Never trust an unsigned webhook.
10. Never download a recording from an arbitrary URL supplied by an untrusted webhook without validation.

## I5. Moderator call UI

Pages/components:
- Assigned telephony task.
- Participant A/B details.
- Start call.
- Call state indicator.
- Add B action where required.
- Consent checklist for A and B.
- Recording state indicator.
- Leave conference action.
- End session action, permission-restricted.
- Error/retry display.
- Session event timeline.

Every action must call the backend and reflect the actual provider response. Do not optimistically show a call as connected before provider confirmation.

## I6. Recording retrieval

Tasks:
1. Receive final recording webhook.
2. Validate recording ID belongs to expected session.
3. Fetch recording using authenticated provider API.
4. Save provider original asset.
5. Inspect file type and codec.
6. Retrieve separate tracks if available.
7. Map A and B with controlled test evidence.
8. Generate final stereo PCM WAV.
9. Validate channels and technical format.
10. Save checksums and processing metadata.
11. Mark task ready for audio QC only after successful validation.

## I7. Phase 6 gate

Test:
- Successful call.
- A does not answer.
- B does not answer.
- B fails to join.
- Moderator drops unexpectedly.
- Participant disconnects.
- Provider webhook repeats.
- Webhook arrives out of order.
- Recording retrieval fails and retries.
- Recording is corrupt.
- One channel is missing.
- 50 concurrent sessions.

---

# PART J — Phase 7: Audio QC and AI transcription

## J1. Audio QC service

Create a read-only analysis service. It must never modify source audio.

Calculate:
- Container and codec.
- Sample rate.
- Bit depth.
- Channels.
- Duration.
- File size.
- Peak.
- RMS.
- Clipping ratio.
- Silence ratio.
- Channel leakage indicator.
- Hash.
- Decode errors.

Use project-configured thresholds. Do not hard-code universal “good audio” thresholds without evidence.

Create QC outcomes:
- `PASS`
- `FAIL`
- `NEEDS_REVIEW`

Create reason codes and comments.

Tests must include:
- Valid mono file.
- Valid stereo file.
- Wrong sample rate.
- Wrong bit depth.
- Wrong channel count.
- Silence.
- Clipping.
- Corrupt file.
- Swapped channels.
- Identical left/right mixed tracks.
- Missing track.

## J2. AI transcription adapter

Create provider-neutral interface:
- submit job
- get job status
- retrieve result
- cancel job if supported

Store:
- provider/model name
- exact model version
- language
- settings
- source asset ID
- job status
- start/end timestamps
- raw response
- normalized transcript
- error details

Never invent confidence scores or speaker labels. Store null if the model does not return them.

## J3. Transcription workflow

1. Audio passes audio QC.
2. System creates transcription job.
3. Job enters queue.
4. Worker fetches private audio through authorized service.
5. Worker submits to configured ASR provider/model.
6. Worker records model/version and settings.
7. Worker stores result and segments.
8. Failed job retries under bounded retry policy.
9. Permanent failure becomes visible to admin.
10. Human review task is created.

## J4. Model evaluation

Create a labelled reference set for every launch language/dialect.

Measure:
- Word Error Rate (WER) where tokenization is appropriate.
- Character Error Rate (CER) where appropriate.
- Speaker-label accuracy if supported.
- Timestamp error.
- Processing time.
- Cost per audio hour.

Do not claim accuracy from a tiny or unrepresentative sample. Record dataset size and evaluation method.

## J5. Phase 7 gate

- QC fixtures pass.
- ASR job lifecycle works.
- Retries work.
- Model provenance is stored.
- Evaluation results are documented.
- No made-up confidence values or speaker labels.

---

# PART K — Phase 8: Human transcription and transcript QC

## K1. Human transcription workspace

Build:
- Assigned task queue.
- Audio player.
- Playback speed controls.
- Seek and segment navigation.
- Transcript editor.
- Speaker labels.
- Timestamp editing.
- Autosave.
- Draft status.
- Submit action.
- Revision history.
- Keyboard shortcuts.

Backend:
- Save draft endpoint.
- Autosave endpoint.
- Submit endpoint.
- Assignment endpoint.
- Revision history endpoint.

Tests:
- Draft survives refresh.
- Concurrent edits are detected.
- Autosave failure is visible.
- Submission locks the submitted version.
- Unauthorized transcriber cannot edit another person's task.

## K2. Transcript QC workspace

Build:
- Audio and transcript side by side.
- Segment playback.
- Approve.
- Reject.
- Return for correction.
- Error categories.
- Reviewer comments.
- QC history.
- Final lock.

Tests:
- Correct transcript can be approved.
- Incorrect transcript can be returned.
- Transcriber sees the reason.
- Revised transcript creates a new version.
- Approved transcript cannot be edited by unauthorized users.
- Reopening requires permission and reason.

## K3. Phase 8 gate

Complete one task end-to-end:
recording -> audio QC -> ASR -> human correction -> transcript QC -> approval.

Save evidence for each state transition.

---

# PART L — Phase 9: Exports and dashboards

## L1. Exports

Create export service for:
- Final WAV.
- Original source recordings where permitted.
- Transcript text.
- Timestamped segments.
- Speaker labels.
- Project/task metadata.
- Language/dialect.
- Audio QC.
- Transcript QC.
- Processing/model provenance.
- Consent metadata subject to permissions.

Formats:
- CSV
- TSV
- JSON
- WAV
- ZIP with manifest and checksums

Tasks:
1. Validate export filters.
2. Check export permissions.
3. Generate export asynchronously for large jobs.
4. Create manifest.
5. Include file checksums.
6. Exclude phone numbers by default.
7. Store export status.
8. Provide short-lived download link.
9. Audit export creation and download.
10. Expire temporary export bundles.

Tests:
- CSV opens correctly.
- JSON matches schema.
- ZIP contents match manifest.
- Hashes match.
- Counts match selected records.
- Unauthorized data is excluded.

## L2. Dashboards

Build:
- Task counts by status.
- Recording hours by mode.
- Daily/monthly target progress.
- Moderator output.
- Transcriber output.
- QC pass/fail.
- Pending queues.
- Failed calls.
- Failed uploads.
- Storage usage.
- Provider usage/cost estimates.

Add filters:
- Project.
- Date range.
- Language.
- Dialect.
- Mode.
- Staff.
- Status.

Tests:
- Compare every dashboard metric with an independent SQL query.
- Test date boundaries and timezone handling.
- Test role and project visibility.
- Test empty datasets.
- Test large date ranges.

## L3. Phase 9 gate

Exports reconcile with database records. Dashboard numbers reconcile with independent queries. Permissions apply to both.

---

# PART M — Phase 10: Security, PWA, deployment and operations

## M1. Security

Implement:
- TLS everywhere.
- Private object storage.
- Encryption at rest.
- Secret manager.
- Webhook signature verification.
- Rate limits.
- Input validation.
- Output encoding.
- CSRF protection where cookie auth is used.
- Secure headers.
- Audit logs.
- Backup encryption.
- Retention enforcement.
- Least-privilege cloud roles.

Tests:
- Dependency vulnerability scan.
- Secret scan.
- Unauthorized API tests.
- Unauthorized recording download tests.
- Webhook signature tests.
- CSRF tests where applicable.
- Backup restore test.
- Audit log integrity review.

## M2. PWA

Tasks:
1. Add `manifest.webmanifest`.
2. Add icons in required sizes.
3. Set app name and short name.
4. Set standalone display mode.
5. Set theme/background colors.
6. Add service worker.
7. Cache only safe static assets by default.
8. Do not cache private audio or participant data in shared browser storage.
9. Add update detection and reload prompt.
10. Add install guidance for supported browsers.
11. Test desktop and mobile installation.
12. Test logout clears sensitive session state.

## M3. Deployment

Create separate environments:
- local
- test/staging
- production

Deploy:
- frontend
- backend
- PostgreSQL
- Redis
- background workers
- private object storage
- reverse proxy/ingress
- monitoring and logs

Tasks:
1. Create infrastructure configuration.
2. Create secrets in cloud secret manager.
3. Configure database backups.
4. Configure object storage lifecycle.
5. Configure health checks.
6. Configure TLS.
7. Configure domain and DNS.
8. Configure alerting.
9. Configure log retention.
10. Configure database migrations as a controlled release step.
11. Create rollback procedure.
12. Create disaster recovery runbook.
13. Test a clean deployment.
14. Test backup restore.

## M4. Performance and load testing

Test target:
- 50 concurrent telephony conferences.
- 50 staff accounts.
- 250 recording hours/day.
- 125 hours/day each mode.

Measure:
- API latency.
- Call setup success.
- Provider call concurrency.
- Worker queue delay.
- Upload throughput.
- Storage growth.
- ASR throughput.
- Database CPU/connections.
- Error rates.
- Recording integrity.

Do not claim 50 concurrent conferences from a local mock test. The provider account must also have the required concurrency entitlement.

## M5. Phase 10 gate

- PWA install works.
- Production deployment is repeatable.
- TLS and secrets are configured.
- Backup restore passes.
- Monitoring alerts work.
- Security checks pass.
- Load test report exists.
- Rollback steps are documented.

---

# PART N — Database model checklist

Create migrations and relationships for at least:

```text
users
roles
permissions
role_permissions
sessions
password_reset_tokens
projects
project_languages
project_memberships
project_audio_rules
participants
participant_project_links
consent_records
tasks
task_assignments
task_status_history
task_comments
provider_accounts
call_sessions
call_participants
call_events
provider_webhook_events
recordings
recording_channels
audio_assets
audio_qc_results
transcription_jobs
transcripts
transcript_segments
transcription_assignments
transcript_revisions
transcript_qc_results
exports
audit_logs
system_settings
```

For each table:
- Define primary key.
- Define foreign keys.
- Define unique constraints.
- Add indexes based on actual query patterns.
- Add created/updated timestamps.
- Define deletion behavior.
- Document sensitive columns.
- Add migration tests.

Do not store task status only in frontend state. Do not store binary audio blobs in PostgreSQL; store object-storage keys and metadata.

---

# PART O — Audio calculations and acceptance

For uncompressed PCM:

- 16 kHz × 16 bits × 1 channel = 256,000 bits/second = 32,000 bytes/second.
- Mono 16 kHz/16-bit = 115.2 MB/hour (decimal).
- Stereo 16 kHz/16-bit = 230.4 MB/hour (decimal).

At 125 hours/day per mode:
- Face-to-face mono: 14.4 GB/day.
- Telephony stereo: 28.8 GB/day.
- Combined: 43.2 GB/day.
- 30 days: 1.296 TB.
- 365 days: approximately 15.77 TB.

These figures exclude source originals, backups, replicas, metadata and derived copies. Confirm retention before final cloud sizing.

Independent audio inspection commands should include:

```bash
ffprobe -v error -show_streams -show_format input.wav
```

Example conversion for a derived mono PCM target (only after source handling is understood):

```bash
ffmpeg -i source_file -ar 16000 -ac 1 -c:a pcm_s16le derived_mono_16k.wav
```

Example conversion for two already-separated, time-aligned participant tracks:

```bash
ffmpeg -i participant_a.wav -i participant_b.wav \
  -filter_complex "[0:a]aresample=16000,aformat=sample_fmts=s16:channel_layouts=mono[a]; \
                   [1:a]aresample=16000,aformat=sample_fmts=s16:channel_layouts=mono[b]; \
                   [a][b]join=inputs=2:channel_layout=stereo[aout]" \
  -map "[aout]" -c:a pcm_s16le -ar 16000 final_stereo.wav
```

This example is valid only when the two input tracks are genuinely separate and correctly aligned. It does not separate a mixed recording. Test the command on controlled fixtures before production use.

---

# PART P — Required automated test layers

Implement all applicable layers:

1. Unit tests: business rules, validation, state transitions, audio calculations.
2. API tests: auth, permissions, CRUD, error handling.
3. Database tests: migrations, constraints, transactions.
4. Integration tests: object storage, queues, provider adapter using isolated test doubles.
5. Contract tests: provider request/response mapping against documented schemas.
6. Audio fixture tests: format, channel mapping, corruption, silence, clipping.
7. Frontend tests: forms, states, permissions, error handling.
8. End-to-end tests: complete user workflows.
9. Security tests: access control, signed URLs, webhook signatures.
10. Load tests: expected concurrent users, calls, uploads and workers.

Never replace integration tests with screenshots.

---

# PART Q — Final requirement tracker

Create/update `docs/BUILD_STATUS.md` with one row per module and one row per requirement ID.

Required columns:

`Requirement ID | Description | Phase | Backend | Database | Frontend | Automated test | Manual test | Evidence path | Status | Blocker`

Every checkbox must have a real link/path to evidence or remain unchecked.

At the end of every session:
1. Run `git status --short`.
2. Review `git diff --check`.
3. Run relevant tests.
4. Update the tracker.
5. Record remaining work.
6. Commit only if the owner/repository workflow permits it.

---

# PART R — Final release checklist

Do not call the project complete until every item is checked:

- [ ] All 16 modules implemented.
- [ ] Every requirement ID has a status and evidence.
- [ ] Authentication and password reset tested.
- [ ] Every role's permissions tested through direct API requests.
- [ ] Project and participant isolation tested.
- [ ] Task lifecycle and invalid transitions tested.
- [ ] Face-to-face browser recording tested.
- [ ] Original and derived files retained separately.
- [ ] Face-to-face PCM format independently verified.
- [ ] Telephony provider accepted by proof-of-capability.
- [ ] Moderator can leave while A and B remain connected.
- [ ] Recording continues after moderator leaves.
- [ ] A and B tracks are genuinely separate.
- [ ] Left/right mapping independently listened to and verified.
- [ ] Telephony PCM WAV properties independently verified.
- [ ] No mixed track was duplicated to fake stereo separation.
- [ ] Audio QC works without modifying source.
- [ ] AI transcription works and model provenance is saved.
- [ ] Human transcription workflow works.
- [ ] Transcript QC and revisions work.
- [ ] Export checksums and manifests validate.
- [ ] Dashboard totals reconcile with database queries.
- [ ] PWA installs on supported browsers.
- [ ] Private recordings are not publicly accessible.
- [ ] Backup restore succeeds.
- [ ] Monitoring and alerting work.
- [ ] 50-conference load test completed with provider confirmation.
- [ ] Production deployment reproduced from documentation.
- [ ] Rollback and incident runbooks exist.
- [ ] No required feature remains a placeholder or stub.

---

# PART S — Copy this as Claude Code's first prompt

Read `docs/` if it exists, then read this entire runbook. Treat it as binding project instructions.

**Do not start by coding the dashboard. Do not skip modules. Do not invent provider capabilities.**

Your first task is Phase 0 only:

1. Inspect the existing repository.
2. Report the actual stack and current implementation.
3. Identify existing working features and tests.
4. Create the documentation structure.
5. Create the requirement traceability table with unique IDs for every requirement in this runbook.
6. Create `docs/BUILD_STATUS.md` with every module and requirement.
7. Identify technical unknowns and external dependencies.
8. Do not delete or rewrite existing working code.
9. Do not mark any feature complete during inspection.
10. Show the exact files created and the exact commands run.

Stop after Phase 0 and request approval.

After approval, implement Phase 1 only. Complete every task in Phase 1, run its checks, attach evidence, update the tracker, and report using the required response format.

Proceed one phase at a time. Do not start the next phase until the current acceptance gate passes.

If a requirement is blocked, mark it BLOCKED and explain the evidence. Do not silently omit it or substitute a fake implementation.

**Your output is working software, not a plan, not mock screens, and not a list of files.**

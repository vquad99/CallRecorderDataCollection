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
| D-012 | 2026-11-09 | Accepted (Phase 0 approval) | MinIO for local storage; managed S3-compatible bucket in cloud. | Same API in both. |
| D-013 | 2026-11-09 | Accepted | Phase 0 document set = runbook C0.2 list; first-pass `TRACEABILITY.md` renamed `REQUIREMENT_TRACEABILITY.md`; runbook copied verbatim to `docs/RUNBOOK_SOURCE.md`. | Runbook supersedes the spec's shorter list. |
| D-014 | 2026-11-09 | Accepted | Status vocabulary = runbook A3 (`NOT STARTED` ... `ACCEPTED`). | Spec 13 and runbook A3 differ; the spec's own initial "Blocked pending provider proof" is not in its list. |
| D-015 | 2026-11-09 | Accepted (Phase 0 approval) | One membership table `project_memberships` (spec: user_project_memberships); one asset table `audio_assets` (runbook I1: recording_assets). | Same concept, one table each; avoids duplicate sources of truth. |
| D-016 | 2026-11-09 | Accepted | Spec v1.0 and runbook both binding; runbook prefixes FTF, AQC, OPS used; extra prefixes for rules the runbook does not prefix. | Owner supplied the runbook after the spec. |
| D-017 | 2026-11-09 | Accepted (Phase 0 approval) | Raw provider payloads and raw ASR responses stored in private object storage, referenced from the database; fields the workflow reads get typed columns. | Keeps the database queryable; runbook I4.2 and J2 require keeping raw data. |

## Open blockers and questions

| ID | Blocks | Question / blocker | Needed from |
|---|---|---|---|
| B-01 | Phase 5-6; 38 TEL requirements | No telephony provider shortlist, no test credentials. | Owner: shortlist (>= 2) or permission to research; then test credentials |
| B-02 | AUDIO-002/013 acceptance | If the provider gives 8 kHz phone audio, the 16 kHz telephony WAV is an up-sampled copy. Acceptable, with that stated in its processing history? | Client |
| B-03 | AUDIO-014/015 acceptance | Browser mics run at 44.1/48 kHz; 16 kHz needs a resample, which is not lossless. Accept a documented resample with the original kept? | Client |
| B-04 | Phase 4 cloud storage, 5, 10 | Cloud provider, account access, region (data residency). | Owner |
| B-05 | Storage sizing, deletion workflow | Retention period for final files, browser originals (6x the size of the derived file) and provider originals. | Client |
| B-06 | Phase 7 | Launch languages and dialects; reference audio with human transcripts for evaluation. | Client |
| B-07 | Phase 7 | GPU compute for Whisper Large-v3 / AI4Bharat (account, budget). | Owner |
| B-08 | Phase 1 | Build machine (aws-dev): Docker and FFmpeg missing; root disk 94 % used (3.5 GB free). | Owner: install Docker + FFmpeg (needs sudo) and free about 15 GB, or name another machine |
| B-09 | Phase 4 device tests, Phase 10 | Domain name + TLS (microphone needs HTTPS outside localhost). | Owner |
| B-10 | TEL-015, PART-006 | Call-recording consent law and provider terms in India; consent script wording. NOT VERIFIED. | Owner / legal |
| B-11 | Push, CI | Remote given 2026-11-09: https://github.com/vquad99/CallRecorderDataCollection. The GitHub account on the build machine has read-only access (push: false). CI host = GitHub Actions once push works. | Owner: grant write access or supply a token with push rights |
| B-12 | Traceability to source text | The spec v1.0 was pasted in chat and is not saved as a file in the repository (the runbook is, as RUNBOOK_SOURCE.md). | Owner: the spec file, if it should be kept verbatim |

## Provider documentation log (GEN-005)

| Provider | Claim | Source URL | Access date | Result |
|---|---|---|---|---|
| - | No provider documentation checked yet | - | - | NOT VERIFIED |

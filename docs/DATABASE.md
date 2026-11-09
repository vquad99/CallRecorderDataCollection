# Database design

Status: proposed (Phase 0). No migration exists yet. PostgreSQL + Alembic (DB-003).

## 1. Conventions (DB-002)

- Primary key `id UUID` on every table.
- `created_at`, `updated_at TIMESTAMPTZ NOT NULL` on every mutable table; all times stored in UTC,
  converted to the project/user timezone only for display and date-boundary reporting.
- Foreign keys declared; deletion behaviour stated per table (section 3). Default `RESTRICT`.
- Status columns are PostgreSQL enums or `CHECK` constraints.
- Soft deletion (`deleted_at`) only on users, projects and participants.
- Indexes on every foreign key and on real filters: `(project_id, status)`, `(assignee, status)`,
  `(created_at)`, `(recording_mode)`; added or removed from measured query plans.
- Workflow state lives here, never only in the frontend (DB-004).
- No audio or other binary blobs; object storage keys and metadata only (DB-006).

## 2. Enumerations

| Enum | Values |
|---|---|
| role_code | SUPER_ADMIN, PROJECT_ADMIN, MODERATOR, TRANSCRIBER, QC_EXECUTIVE, CLIENT_VIEWER |
| user_status | ACTIVE, DISABLED |
| project_status | DRAFT, ACTIVE, PAUSED, COMPLETED, ARCHIVED |
| recording_mode | TELEPHONY, FACE_TO_FACE |
| task_status | DRAFT, ASSIGNED, IN_PROGRESS, RECORDED, AUDIO_QC, TRANSCRIPTION_PENDING, TRANSCRIPTION_IN_PROGRESS, TRANSCRIPT_QC, APPROVED, REJECTED, RETURNED, CANCELLED, ON_HOLD |
| consent_status | PENDING, GIVEN, REFUSED, WITHDRAWN |
| call_state | CREATED, CALLING_A, A_CONNECTED, ADDING_B, B_CONNECTED, MODERATOR_CONNECTED, CONSENT_PENDING, CONSENT_CONFIRMED, RECORDING, MODERATOR_LEFT, PARTICIPANTS_CONTINUING, COMPLETED, FAILED, CANCELLED |
| asset_kind | PROVIDER_ORIGINAL_TRACK, PROVIDER_ORIGINAL_MIXED, TELEPHONY_FINAL_STEREO, CONSENT_RECORDING, BROWSER_ORIGINAL, FTF_DERIVED_PCM, TRANSCRIPT_FILE, EXPORT_PACKAGE |
| qc_outcome | PASS, FAIL, NEEDS_REVIEW |
| job_status | QUEUED, RUNNING, SUCCEEDED, FAILED, DEAD_LETTER, CANCELLED |

## 3. Tables (DB-001: spec 8 + runbook N, E4, F1, I1)

S = sensitive column (personal data or secret reference), protection noted in SECURITY.md.

| Table | Key columns | Constraints / indexes | On delete |
|---|---|---|---|
| users | email (S), display_name (S), password_hash (S), status, mfa_secret_enc (S), last_login_at, deleted_at | unique lower(email) | soft delete |
| roles | code, name | unique code | restrict |
| permissions | code, description | unique code | restrict |
| role_permissions | role_id, permission_id | unique pair | cascade with role |
| sessions | user_id, token_hash (S), created_at, last_seen_at, expires_at, revoked_at, ip (S), user_agent | index (user_id), unique token_hash | cascade with user |
| password_reset_tokens | user_id, token_hash (S), expires_at, used_at | unique token_hash | cascade with user |
| projects | code, name, status, recording_modes, daily targets per mode, phone_visibility_policy, consent_policy_version, asr_enabled (default false), asr_provider, asr_settings, deleted_at | unique code; index status | soft delete |
| project_languages | project_id, language_code, dialect | unique (project_id, language_code, dialect) | cascade |
| project_memberships | user_id, project_id, added_by | unique (user_id, project_id) | cascade |
| user_roles | user_id, role_id | primary key (user_id, role_id) | cascade with user |
| login_attempts | email, ip, succeeded | index (email, created_at), (ip, created_at) | kept for throttling |
| project_audio_rules | project_id, mode, sample_rate, bit_depth, channels, qc thresholds (silence %, clipping %, min/max duration, leakage) | unique (project_id, mode) | cascade |
| project_transcription_guidelines | project_id, version, guideline_text, verbatim_rules | unique (project_id, version) | restrict |
| project_retention_rules | project_id, asset_kind, retain_days, delete_action | unique (project_id, asset_kind) | cascade |
| participants | participant_code (P + 6 digits, from `participant_code_seq`), display_label (S), phone_e164_enc (S), phone_hash (S), phone_hint (last 2 digits), language_code, dialect, notes (S), created_by, deleted_at, deleted_by, deletion_reason | unique participant_code; index phone_hash (duplicate detection) | soft delete |
| participant_project_links | participant_id, project_id | unique pair | restrict |
| consent_records | participant_id, project_id, task_id, status, method, policy_version, captured_by, note (call_session_id and consent_asset_id arrive with Phases 4-6) | index (participant_id, task_id) | restrict |
| tasks | task_code (T + 6 digits, from `task_code_seq`), project_id, recording_mode, status, held_from, priority, due_at, participant_a_id, participant_b_id (must differ), reason_code, created_by | index (project_id, status), (due_at) | restrict |
| task_assignments | task_id, user_id, role_code, active, assigned_by, reason, assigned_at, ended_at | partial unique (task_id, role_code) where active | restrict |
| task_status_history | task_id, from_status, to_status, actor_id, reason_code, comment, at | index (task_id, at) | restrict |
| task_comments | task_id, author_id, body, internal (bool) | index (task_id) | restrict |
| provider_accounts | provider, label, region, concurrency_limit, credentials_ref (secret-manager reference only) | unique (provider, label) | restrict |
| call_sessions | task_id, provider_account_id, conference_ref, state, started_at, ended_at, moderator_left_at, recording_state, failure_code, failure_detail_safe | unique conference_ref; index state | restrict |
| call_participants | call_session_id, participant_id (null for moderator), leg_role (A, B, MODERATOR), provider_call_ref, joined_at, left_at | unique provider_call_ref | cascade |
| call_events | call_session_id, event_type, provider_event_id, from_state, to_state, occurred_at, received_at | index (call_session_id, occurred_at) | cascade |
| provider_webhook_events | provider, provider_event_id, signature_valid, received_at, processed_at, status, attempts, last_error, raw_metadata_ref | unique (provider, provider_event_id) | restrict |
| recordings | task_id, mode, state (RECORDING, INTERRUPTED, UPLOADED, PROCESSING, READY, FAILED, DISCARDED), created_by, native_sample_rate, channel_count (channels captured = original file's channels), device_channel_count (browser-reported, nullable), channel_handling (server-set), echo_cancellation, noise_suppression, auto_gain_control, device_label, user_agent, chunks_received, frames_received (per channel; was samples_received until migration 0005), interrupted, interruption_reason, started_at, ended_at, failure_reason (call_session_id arrives in Phase 6) | index task_id; at most one open recording per task | restrict |
| recording_chunks | recording_id, seq, sha256, size_bytes, storage_key, object_deleted | unique (recording_id, seq) | restrict |
| recording_channels | recording_id, channel_index (0 left, 1 right), participant_id, source_asset_id, verified_separate, verification_note | unique (recording_id, channel_index) | cascade |
| audio_assets | recording_id, kind, parent_asset_id, storage_key, version, container, codec, sample_format, sample_rate, bit_depth, channels, duration_ms, size_bytes, sha256, peak_dbfs, clip_count, clip_pct, silence_pct, rms_dbfs, provider_codec, provider_recording_spec | unique (storage_key, version); index sha256 | retention workflow |
| asset_processing_steps | asset_id, seq, tool, tool_version, parameters, input_asset_id, output_sha256 | unique (asset_id, seq) | cascade |
| audio_qc_results | audio_asset_id, rule_set_version, outcome, reason_code, metric columns, reviewer_id, comment, reviewed_at | index audio_asset_id | restrict |
| transcription_jobs | audio_asset_id, provider, model_name, model_version, settings, language_code, dialect, status, attempts, started_at, finished_at, raw_response_ref, last_error | index status | restrict |
| transcripts | task_id, source (AI, HUMAN), transcription_job_id, current_version, status, locked, locked_at | unique (task_id, source) | restrict |
| transcript_revisions | transcript_id, version, author_id, created_at, submitted (bool) | unique (transcript_id, version) | restrict |
| transcript_segments | revision_id, seq, start_ms, end_ms, speaker_label (null if unknown), text, confidence (null if not given) | unique (revision_id, seq) | cascade |
| transcription_assignments | task_id, user_id, status, due_at | partial unique (task_id) where active | restrict |
| transcript_qc_results | transcript_id, revision_id, outcome, error_category, reviewer_id, comment, reviewed_at | index transcript_id | restrict |
| exports | project_id, requested_by, filters, formats, status, file_count, manifest_sha256, includes_personal_data, authorized_by, expires_at | index (project_id, created_at) | restrict |
| export_items | export_id, task_id, asset_id, path_in_package, sha256 | unique (export_id, path_in_package) | cascade |
| audit_logs | actor_id, action, entity_type, entity_id, project_id, before_summary, after_summary, ip (S), user_agent, request_id, occurred_at | append-only (no UPDATE/DELETE grant); index (entity_type, entity_id), (occurred_at) | never deleted inside retention |
| system_settings | key, value_type, value_text, value_int, updated_by | unique key | restrict |

Raw provider payloads are not stored as opaque blobs in the database. Fields the workflow reads get
their own columns; the raw payload, where kept for audit, goes to private object storage
(`raw_metadata_ref`, `raw_response_ref`).

## 4. Sensitive columns (DB-005)

| Column | Protection |
|---|---|
| users.email, users.display_name | access by `users.manage` or self |
| users.password_hash, sessions.token_hash, password_reset_tokens.token_hash | never returned by any API (AUTH-015) |
| users.mfa_secret_enc, participants.phone_e164_enc | application-level encryption, key in secret manager |
| participants.phone_hash | keyed hash for duplicate detection; not reversible |
| participants.display_label | project-scoped access |
| sessions.ip, audit_logs.ip | admin and audit access only |
| provider_accounts.credentials_ref | reference only; secrets live in the secret manager |

## 5. Storage sizing (spec 9, runbook O, CAP-005)

16 kHz x 16 bit x 1 channel = 256 000 bit/s = 32 000 byte/s = 115.2 MB per hour (decimal).

| Asset | Per hour | At 125 h/day | 30 days | 365 days |
|---|---:|---:|---:|---:|
| Face-to-face derived (mono) | 115.2 MB | 14.4 GB | 432 GB | 5.26 TB |
| Telephony final (stereo) | 230.4 MB | 28.8 GB | 864 GB | 10.51 TB |
| **Spec/runbook total** | | **43.2 GB** | **1.296 TB** | **15.77 TB** |

Not in those figures, needed by this design, sized by the retention decision (B-05):

| Extra asset | Per hour | At 125 h/day |
|---|---:|---:|
| Face-to-face browser original (32-bit float, 48 kHz, mono) | 691.2 MB | 86.4 GB |
| Telephony provider originals, two 8 kHz 16-bit mono tracks | 115.2 MB | 14.4 GB |
| Telephony provider originals, two 16 kHz 16-bit mono tracks | 230.4 MB | 28.8 GB |

Keeping full browser originals for the whole retention period roughly triples storage. Backups,
replicas and export bundles are extra.

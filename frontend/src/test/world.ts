// Test-only: one consistent fake backend for every page (Option C). Each test starts from
// worldHandlers() and replaces only what it is about.
import type { Handler } from "./fakeApi";

export const PROJECT = {
  id: "p1",
  code: "HINDI",
  name: "Hindi conversations",
  status: "ACTIVE",
  allows_telephony: true,
  allows_face_to_face: true,
  target_telephony_hours_per_day: "10.00",
  target_face_to_face_hours_per_day: "5.00",
  created_at: "2026-11-09T00:00:00Z",
  description: "",
  phone_visibility_policy: "ADMINS_ONLY",
  consent_policy_version: "1",
  consent_text: "",
  status_reason: null,
  status_changed_at: null,
  languages: [{ language_code: "hi", dialect: "" }],
  audio_rules: [
    {
      mode: "FACE_TO_FACE",
      sample_rate: 16000,
      bit_depth: 16,
      channels: 1,
      max_silence_pct: "25.00",
      max_clipping_pct: null,
      min_duration_seconds: 0,
      max_duration_seconds: null,
    },
  ],
  retention_rules: [{ asset_kind: "BROWSER_ORIGINAL", retain_days: 90 }],
  accepts_new_work: true,
};

export const PARTICIPANT = {
  id: "a1",
  participant_code: "P000001",
  language_code: "hi",
  dialect: "",
  display_label: "Asha",
  phone: "+919876543210",
  has_phone: true,
  email: "asha@example.org",
  has_email: true,
  consent_status: "GIVEN",
  consent_review: "PENDING",
  link_active: true,
  consent_visible: true,
  notes: "",
  deleted: false,
  created_at: "2026-11-09T00:00:00Z",
};
export const PARTICIPANT_B = {
  ...PARTICIPANT,
  id: "b1",
  participant_code: "P000002",
  display_label: "Bina",
};

const party = (p: typeof PARTICIPANT) => ({
  id: p.id,
  participant_code: p.participant_code,
  consent_status: null,
  consent_at: null,
});

export const TASK = {
  id: "t1",
  task_code: "T000001",
  project_id: "p1",
  recording_mode: "FACE_TO_FACE",
  status: "ASSIGNED",
  priority: "NORMAL",
  due_at: null,
  created_at: "2026-11-09T00:00:00Z",
  held_from: null,
  reason_code: null,
  participant_a: party(PARTICIPANT),
  participant_b: party(PARTICIPANT_B),
  moderator_id: "m1",
  moderator_name: "Mona Moderator",
  allowed_transitions: ["ON_HOLD", "CANCELLED"],
  reasons: {
    ON_HOLD: ["OTHER", "WAITING_FOR_PARTICIPANT"],
    CANCELLED: ["CLIENT_REQUEST", "OTHER"],
  },
  can_assign: true,
  is_moderator: true,
};

export const USER = {
  id: "u2",
  email: "mona@example.org",
  display_name: "Mona Moderator",
  status: "ACTIVE",
  roles: ["MODERATOR"],
  mfa_enabled: false,
  password_set: true,
  last_login_at: null,
  created_at: "2026-11-09T00:00:00Z",
};

export const MEMBER = {
  user_id: "m1",
  email: "mona@example.org",
  display_name: "Mona Moderator",
  roles: ["MODERATOR"],
  status: "ACTIVE",
  added_at: "2026-11-09T00:00:00Z",
};

export const MEMBER_2 = {
  ...MEMBER,
  user_id: "u4",
  email: "ravi@example.org",
  display_name: "Ravi Moderator",
};

export const SETTINGS = [
  {
    key: "capacity.staff_accounts",
    value: 50,
    min_value: 1,
    max_value: 100000,
    updated_at: "2026-11-09T00:00:00Z",
  },
  {
    key: "capacity.total_hours_per_day",
    value: 250,
    min_value: 1,
    max_value: 1000000,
    updated_at: "2026-11-09T00:00:00Z",
  },
];

/** Every permission the interface checks; tests narrow this per role. */
export const PORTAL = {
  participant_code: "P000001",
  project_name: "Hindi conversations",
  language_code: "hi",
  consent_policy_version: "2",
  consent_text: "I agree that my voice is recorded.",
  consent_status: null,
  consent_at: null,
  consent_review: null,
  consent_review_note: "",
  sessions: [
    {
      task_code: "T000001",
      mode: "FACE_TO_FACE",
      day: "2026-11-01T10:00:00Z",
      state: "Accepted",
      minutes: 22.5,
    },
  ],
  accepted_minutes: 22.5,
  link_expires_at: "2026-12-10T00:00:00Z",
};

export const DASHBOARD = {
  view: "manager",
  timezone: "Asia/Kolkata",
  project_id: null,
  projects: [{ id: "p1", code: "HINDI", name: "Hindi conversations" }],
  recorded_hours: 12.5,
  approved_hours: 8,
  recordings: 30,
  target_hours_per_day: 4,
  today_hours: 1.5,
  by_mode: [
    {
      mode: "FACE_TO_FACE",
      recorded_hours: 7.5,
      approved_hours: 5,
      recordings: 18,
      target_hours_per_day: 2,
    },
    {
      mode: "TELEPHONY",
      recorded_hours: 5,
      approved_hours: 3,
      recordings: 12,
      target_hours_per_day: 2,
    },
  ],
  daily: Array.from({ length: 30 }, (_, i) => ({
    day: `2026-10-${String(i + 1).padStart(2, "0")}`,
    recorded_hours: (i % 5) * 0.4,
    approved_hours: (i % 5) * 0.25,
  })),
  tasks_total: 40,
  tasks_approved: 22,
  tasks_by_status: { APPROVED: 22, AUDIO_QC: 6, IN_PROGRESS: 4, ASSIGNED: 8 },
  qc: {
    passed: 22,
    rejected: 1,
    returned: 2,
    waiting: 6,
    auto_pass: 4,
    auto_review: 1,
    auto_fail: 1,
  },
  queues: {
    waiting_for_qc: 6,
    processing: 0,
    failed_processing: 1,
    interrupted: 0,
    stale_uploads: 0,
    on_hold: 0,
  },
  team: [{ name: "Max Moderator", recordings: 30, recorded_hours: 12.5 }],
  storage_bytes: 3_200_000_000,
};

export const ALL_PERMISSIONS = [
  "settings.manage",
  "users.manage",
  "audit.view",
  "projects.create",
  "projects.view",
  "projects.manage",
  "projects.members",
  "participants.view",
  "participants.manage",
  "participants.contact",
  "participants.export",
  "consent.capture",
  "consent.view",
  "tasks.view",
  "tasks.assign",
  "recordings.create",
  "recordings.view",
  "recordings.download",
  "dashboard.view",
  "notes.view",
];

const page = <T>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 25 });
const ok =
  (body: unknown, status = 200): Handler =>
  () => [status, body];

export function worldHandlers(): Record<string, Handler> {
  return {
    "GET /api/v1/version": ok({ name: "ccp", version: "1.0.0", environment: "test" }),
    "GET /health/ready": ok({ status: "ready", checks: { database: "ok", redis: "ok" } }),
    "GET /api/v1/system/status": ok({
      status: "ready",
      checks: { database: "ok", redis: "ok" },
      version: { name: "ccp", version: "1.0.0", environment: "test" },
    }),
    "GET /api/v1/projects": ok(page([PROJECT])),
    "GET /api/v1/projects/p1": ok(PROJECT),
    "GET /api/v1/projects/p1/members": ok([MEMBER, MEMBER_2]),
    "GET /api/v1/projects/p1/export/summary": ok({
      recordings: 1,
      audio_bytes: 1_000_000,
      file_name: "both_HINDI_20261111.zip",
    }),
    "GET /api/v1/projects/p1/member-candidates": ok([
      { user_id: "u3", email: "tara@example.org", display_name: "Tara", roles: ["QC_EXECUTIVE"] },
    ]),
    "GET /api/v1/projects/p1/participants": ok(page([PARTICIPANT, PARTICIPANT_B])),
    "GET /api/v1/projects/p1/participants/a1/consent": ok([]),
    "GET /api/v1/tasks": ok(page([TASK])),
    "GET /api/v1/dashboard": ok(DASHBOARD),
    "GET /api/v1/portal/me": ok(PORTAL),
    "GET /api/v1/tasks/t1": ok(TASK),
    "GET /api/v1/tasks/t1/timeline": ok([
      { at: "2026-11-09T00:00:00Z", kind: "status", actor: "Ada", text: "created -> DRAFT" },
    ]),
    "GET /api/v1/tasks/t1/recordings": ok([]),
    "GET /api/v1/audit-logs": ok(
      page([
        {
          id: "e1",
          created_at: "2026-11-09T00:00:00Z",
          actor_email: "ada@example.org",
          action: "project.created",
          entity_type: "project",
          entity_id: "p1",
          project_id: "p1",
          before: null,
          after: { code: "HINDI" },
          ip: null,
          request_id: null,
        },
      ]),
    ),
    "GET /api/v1/users": ok(page([USER])),
    "GET /api/v1/users/u2": ok(USER),
    "GET /api/v1/settings": ok(SETTINGS),
    "GET /api/v1/auth/sessions": ok([
      {
        id: "s1",
        created_at: "2026-11-09T00:00:00Z",
        last_seen_at: "2026-11-09T00:00:00Z",
        expires_at: "2026-11-10T00:00:00Z",
        ip: null,
        user_agent: "test",
        current: true,
      },
    ]),
  };
}

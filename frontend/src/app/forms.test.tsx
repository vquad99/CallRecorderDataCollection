// Every form (owner's test list, Option C).
// Requirements: FND-016, FND-018, FND-019, SEC-006
//
// For each form: what was entered reaches the server in exactly one request; a second click while
// waiting sends nothing more; and a validation error (naming the field), a conflict, a server error
// (with its reference) and a lost connection are each shown without losing what was typed. A guard
// counts the <form> elements in the source so a new form cannot ship without an entry here.
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, signedInAs, type Handler } from "../test/fakeApi";
import { ALL_PERMISSIONS, PROJECT, TASK, USER, worldHandlers } from "../test/world";

afterEach(() => vi.unstubAllGlobals());

type Step = () => Promise<void>;
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const field = (label: string) =>
  screen.getByLabelText(new RegExp(`^${escape(label)}( \\*)?$`)) as HTMLInputElement;
const type =
  (label: string, value: string): Step =>
  async () => {
    await userEvent.clear(field(label));
    await userEvent.type(field(label), value);
  };
const choose =
  (label: string, value: string): Step =>
  async () => {
    // Options can arrive after the page (e.g. the project's moderators): wait for this one.
    await waitFor(() =>
      expect(
        Array.from((field(label) as unknown as HTMLSelectElement).options).map((o) => o.value),
      ).toContain(value),
    );
    await userEvent.selectOptions(field(label), value);
  };
const click =
  (name: string | RegExp): Step =>
  async () => {
    await userEvent.click((await screen.findAllByRole("button", { name }))[0] as HTMLElement);
  };
const tick =
  (label: string): Step =>
  async () => {
    await userEvent.click(screen.getByRole("checkbox", { name: label }));
  };

interface FormSpec {
  source: string; // file holding the <form>
  url: string;
  ready: RegExp; // text present once the page has loaded
  open?: Step[]; // steps that reveal the form
  fill: Step[];
  submit: string;
  write: string; // "METHOD /path" of the request the form sends
  reply: [number, unknown];
  body?: Record<string, unknown>; // part of the request body that must match
  kept: string; // a text field whose value must survive an error
  anonymous?: boolean;
  handlers?: Record<string, Handler>;
}

const MFA_ME = { ...ME, permissions: ALL_PERMISSIONS, mfa_enabled: true };

const FORMS: Record<string, FormSpec> = {
  "sign in": {
    source: "src/auth/LoginPage.tsx",
    url: "/login",
    ready: /^Sign in$/,
    fill: [type("Email", "ada@example.org"), type("Password", "a-long-password")],
    submit: "Sign in",
    write: "POST /api/v1/auth/login",
    reply: [200, ME],
    body: { email: "ada@example.org", password: "a-long-password" },
    kept: "Email",
    anonymous: true,
  },
  "forgot password": {
    source: "src/auth/ForgotPasswordPage.tsx",
    url: "/forgot-password",
    ready: /Reset your password/,
    fill: [type("Email", "ada@example.org")],
    submit: "Send reset link",
    write: "POST /api/v1/auth/password/forgot",
    reply: [202, { status: "sent" }],
    body: { email: "ada@example.org" },
    kept: "Email",
    anonymous: true,
  },
  "reset password": {
    source: "src/auth/ResetPasswordPage.tsx",
    url: "/reset-password?token=tok123",
    ready: /Set a new password/,
    fill: [
      type("New password", "brand-new-passphrase"),
      type("Repeat new password", "brand-new-passphrase"),
    ],
    submit: "Set password",
    write: "POST /api/v1/auth/password/reset",
    reply: [204, null],
    body: { token: "tok123" },
    kept: "New password",
    anonymous: true,
  },
  "change password": {
    source: "src/features/account/AccountPage.tsx",
    url: "/account",
    ready: /Signed-in devices/,
    fill: [
      type("Current password", "old-password-123"),
      type("New password", "new-password-456789"),
    ],
    submit: "Change password",
    write: "POST /api/v1/auth/password/change",
    reply: [204, null],
    kept: "Current password",
  },
  "confirm two-step sign-in": {
    source: "src/features/account/AccountPage.tsx",
    url: "/account",
    ready: /Signed-in devices/,
    open: [click("Turn on two-step sign-in")],
    fill: [type("Authenticator code", "123456")],
    submit: "Confirm",
    write: "POST /api/v1/auth/mfa/confirm",
    reply: [204, null],
    body: { code: "123456" },
    kept: "Authenticator code",
    handlers: {
      "POST /api/v1/auth/mfa/enroll": () => [200, { secret: "ABC", otpauth_uri: "otpauth://x" }],
    },
  },
  "turn off two-step sign-in": {
    source: "src/features/account/AccountPage.tsx",
    url: "/account",
    ready: /Signed-in devices/,
    fill: [type("Password", "a-long-password"), type("Authenticator code", "654321")],
    submit: "Turn off two-step sign-in",
    write: "POST /api/v1/auth/mfa/disable",
    reply: [204, null],
    kept: "Password",
    handlers: { "GET /api/v1/auth/me": () => [200, MFA_ME] },
  },
  "add user": {
    source: "src/features/users/UserCreatePage.tsx",
    url: "/admin/users/new",
    ready: /Add user/,
    fill: [type("Email", "new@example.org"), type("Name", "New Person"), tick("Moderator")],
    submit: "Add and send invitation",
    write: "POST /api/v1/users",
    reply: [201, { user: USER, invite_sent: true }],
    body: { email: "new@example.org", display_name: "New Person", roles: ["MODERATOR"] },
    kept: "Email",
  },
  "edit user": {
    source: "src/features/users/UserDetailPage.tsx",
    url: "/admin/users/u2",
    ready: /Disable account/,
    fill: [type("Name", "Mona M")],
    submit: "Save changes",
    write: "PATCH /api/v1/users/u2",
    reply: [200, USER],
    body: { display_name: "Mona M" },
    kept: "Name",
  },
  "capacity targets": {
    source: "src/features/settings/SettingsPage.tsx",
    url: "/admin/settings",
    ready: /Allowed: 1 to 100000/,
    fill: [type("Staff accounts", "60")],
    submit: "Save targets",
    write: "PATCH /api/v1/settings",
    reply: [200, []],
    body: { values: { "capacity.staff_accounts": 60 } },
    kept: "Staff accounts",
  },
  "new project": {
    source: "src/features/projects/ProjectForm.tsx",
    url: "/projects/new",
    ready: /New project/,
    fill: [type("Project code", "TAMIL"), type("Name", "Tamil talk")],
    submit: "Create project",
    write: "POST /api/v1/projects",
    reply: [201, PROJECT],
    body: { code: "TAMIL", name: "Tamil talk" },
    kept: "Name",
  },
  "edit project": {
    source: "src/features/projects/ProjectForm.tsx",
    url: "/projects/p1",
    ready: /HINDI · Hindi conversations/,
    fill: [type("Name", "Renamed")],
    submit: "Save project",
    write: "PATCH /api/v1/projects/p1",
    reply: [200, PROJECT],
    body: { name: "Renamed" },
    kept: "Name",
  },
  "project status": {
    source: "src/features/projects/tabs.tsx",
    url: "/projects/p1",
    ready: /HINDI · Hindi conversations/,
    fill: [type("Reason", "Client asked to pause")],
    submit: "Change status",
    write: "POST /api/v1/projects/p1/status",
    reply: [200, PROJECT],
    body: { reason: "Client asked to pause" },
    kept: "Reason",
  },
  "find people to add": {
    source: "src/features/projects/tabs.tsx",
    url: "/projects/p1/team",
    ready: /ravi@example\.org/,
    fill: [type("Find by name or email", "tara")],
    submit: "Search",
    write: "GET /api/v1/projects/p1/member-candidates",
    reply: [200, []],
    kept: "Find by name or email",
  },
  "audio rules": {
    source: "src/features/projects/tabs.tsx",
    url: "/projects/p1/audio",
    ready: /^Face-to-face$/,
    fill: [type("Sample rate (Hz)", "22050")],
    submit: "Save audio rules",
    write: "PUT /api/v1/projects/p1/audio-rules",
    reply: [200, PROJECT],
    kept: "Sample rate (Hz)",
  },
  languages: {
    source: "src/features/projects/tabs.tsx",
    url: "/projects/p1/languages",
    ready: /^Add language$/,
    fill: [type("Language code", "ta")],
    submit: "Add language",
    write: "PUT /api/v1/projects/p1/languages",
    reply: [200, PROJECT],
    kept: "Language code",
  },
  retention: {
    source: "src/features/projects/tabs.tsx",
    url: "/projects/p1/retention",
    ready: /Days to keep each kind of file/,
    fill: [type("Face-to-face 16 kHz WAV", "30")],
    submit: "Save retention",
    write: "PUT /api/v1/projects/p1/retention",
    reply: [200, PROJECT],
    kept: "Face-to-face 16 kHz WAV",
  },
  guidelines: {
    source: "src/features/projects/tabs.tsx",
    url: "/projects/p1/guidelines",
    ready: /Speak clearly/,
    fill: [type("Guideline text", "Do not interrupt.")],
    submit: "Publish version",
    write: "POST /api/v1/projects/p1/guidelines",
    reply: [201, { version: 2, guideline_text: "x", verbatim: true, created_at: "" }],
    body: { guideline_text: "Do not interrupt." },
    kept: "Guideline text",
  },
  "add participant": {
    source: "src/features/projects/ParticipantsTab.tsx",
    url: "/projects/p1/participants",
    ready: /P000002/,
    open: [click("Add participant")],
    fill: [type("Name or label", "Chandra"), type("Language code", "hi")],
    submit: "Add participant",
    write: "POST /api/v1/projects/p1/participants",
    reply: [201, { ...PROJECT, id: "c1" }],
    body: { display_label: "Chandra", language_code: "hi" },
    kept: "Name or label",
  },
  "correct participant": {
    source: "src/features/projects/ParticipantsTab.tsx",
    url: "/projects/p1/participants",
    ready: /P000002/,
    open: [click("Correct")],
    fill: [type("Name or label", "Asha K")],
    submit: "Save P000001",
    write: "PATCH /api/v1/projects/p1/participants/a1",
    reply: [200, {}],
    body: { display_label: "Asha K" },
    kept: "Name or label",
  },
  "new task": {
    source: "src/features/tasks/TaskCreatePage.tsx",
    url: "/tasks/new",
    ready: /HINDI Hindi conversations/,
    fill: [
      choose("Project (active projects)", "p1"),
      choose("Recording mode", "FACE_TO_FACE"),
      choose("Participant A", "a1"),
      choose("Participant B", "b1"),
    ],
    submit: "Create task",
    write: "POST /api/v1/tasks",
    reply: [201, TASK],
    body: { project_id: "p1", participant_a_id: "a1", participant_b_id: "b1" },
    kept: "Due date",
  },
  "task status": {
    source: "src/features/tasks/TaskDetailPage.tsx",
    url: "/tasks/t1",
    ready: /Task T000001/,
    fill: [choose("Move to", "ON_HOLD"), choose("Reason", "OTHER"), type("Comment", "Waiting")],
    submit: "Apply",
    write: "POST /api/v1/tasks/t1/transition",
    reply: [200, TASK],
    body: { to: "ON_HOLD", reason_code: "OTHER", comment: "Waiting" },
    kept: "Comment",
  },
  "assign moderator": {
    source: "src/features/tasks/TaskDetailPage.tsx",
    url: "/tasks/t1",
    ready: /Task T000001/,
    fill: [choose("Moderator", "u4"), type("Reason for reassigning", "Mona is away")],
    submit: "Reassign",
    write: "POST /api/v1/tasks/t1/assign",
    reply: [200, TASK],
    body: { user_id: "u4", reason: "Mona is away" },
    kept: "Reason for reassigning",
  },
  "task comment": {
    source: "src/features/tasks/TaskDetailPage.tsx",
    url: "/tasks/t1",
    ready: /Task T000001/,
    fill: [type("Add a comment", "Called twice, no answer")],
    submit: "Add comment",
    write: "POST /api/v1/tasks/t1/comments",
    reply: [201, { at: "", kind: "comment", actor: "Ada", text: "x" }],
    body: { body: "Called twice, no answer" },
    kept: "Add a comment",
  },
};

const SOURCES = import.meta.glob("../**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const SIGNED_OUT: Record<string, Handler> = {
  "GET /api/v1/auth/csrf": () => [204, null],
  "GET /api/v1/auth/me": () => [401, { error: { code: "UNAUTHENTICATED", message: "Sign in" } }],
};

async function openForm(spec: FormSpec, write: Handler) {
  const handlers = { ...worldHandlers(), ...spec.handlers, [spec.write]: write };
  const api = fakeApi(
    spec.anonymous ? { ...handlers, ...SIGNED_OUT } : signedInAs(ALL_PERMISSIONS, handlers),
  );
  renderAt(spec.url);
  await screen.findAllByText(spec.ready, {}, { timeout: 3000 });
  for (const step of spec.open ?? []) await step();
  for (const step of spec.fill) await step();
  const writes = () =>
    api.calls.filter((c) => `${c.method} ${c.path.split("?")[0]}` === spec.write);
  return { writes, submit: () => screen.getByRole("button", { name: spec.submit }) };
}

describe("form inventory", () => {
  it("has an entry for every <form> in the source", () => {
    const missing: string[] = [];
    for (const [path, text] of Object.entries(SOURCES)) {
      if (path.includes(".test.")) continue;
      const forms = (text.match(/<form\b/g) ?? []).length;
      const file = `src/${path.replace(/^\.\.\//, "")}`;
      const specs = Object.values(FORMS).filter((f) => f.source === file).length;
      if (specs < forms) missing.push(`${file}: ${forms} form(s), ${specs} entr(y/ies)`);
    }
    expect(missing).toEqual([]);
  });
});

const FAILURES: [string, Handler, RegExp][] = [
  [
    "a validation error naming the field",
    () => [
      422,
      {
        error: {
          code: "VALIDATION_ERROR",
          message: "Request validation failed",
          details: [{ loc: ["body", "display_name"], msg: "Field required", type: "missing" }],
        },
      },
    ],
    /Display name: Field required/,
  ],
  [
    "a conflict",
    () => [409, { error: { code: "CONFLICT", message: "Someone changed this first" } }],
    /Someone changed this first/,
  ],
  [
    "a server error with its reference",
    () => [
      500,
      {
        error: { code: "INTERNAL_ERROR", message: "Internal server error", request_id: "req-form" },
      },
    ],
    /req-form/,
  ],
  ["a lost connection", () => "NETWORK", /Cannot reach the server/],
];

const alertsText = () =>
  screen
    .queryAllByRole("alert")
    .map((a) => a.textContent ?? "")
    .join(" | ");

describe.each(Object.entries(FORMS))("%s form", (_, spec) => {
  it("sends what was entered in exactly one request", async () => {
    const { writes, submit } = await openForm(spec, () => spec.reply);
    await userEvent.click(submit());
    await waitFor(() => expect(writes()).toHaveLength(1));
    if (spec.body) expect(writes()[0]?.body).toMatchObject(spec.body);
  });

  it("sends nothing more when clicked again while waiting", async () => {
    let release: (() => void) | null = null;
    const { writes, submit } = await openForm(
      spec,
      () =>
        new Promise((resolve) => {
          release = () => resolve(spec.reply);
        }) as ReturnType<Handler>,
    );
    await userEvent.click(submit());
    await waitFor(() => expect(writes()).toHaveLength(1));
    const button = screen.queryByRole("button", { name: spec.submit });
    if (button) {
      expect(button).toBeDisabled();
      await userEvent.click(button);
    }
    expect(writes()).toHaveLength(1);
    (release as unknown as () => void)();
    await waitFor(() => expect(screen.queryByRole("button", { busy: true })).toBeNull());
  });

  it("shows each kind of failure and keeps what was typed", async () => {
    let failure: Handler = () => [500, {}];
    const { writes, submit } = await openForm(spec, (b, u) => failure(b, u));
    const typed = field(spec.kept).value;
    for (const [kind, fail, says] of FAILURES) {
      failure = fail;
      const before = writes().length;
      await userEvent.click(submit());
      await waitFor(() => expect(writes()).toHaveLength(before + 1));
      await waitFor(() => expect(alertsText()).toMatch(says), { timeout: 2000 }).catch(() => {
        throw new Error(`${kind}: alerts read "${alertsText()}"`);
      });
      expect(field(spec.kept).value).toBe(typed);
    }
  });
});

// Phone calls on a telephony task (D-101, D-103): the moderator starts the call, ticks the
// checklist and closes it; the page shows only what the server says and keeps what is typed while
// it refreshes; a call that needs a person offers the provider's calls to choose from; a call can
// be cancelled while its recording is fetched; the finished recording can be listened to; and a
// Super Admin gives a moderator their phone seat. Moderators read plain words; the provider's own
// answers are in the Super Admin's technical log; recording waits for both people's consent.
// Requirements: TEL-002, TEL-018, TEL-036, TEL-037, GEN-004
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, TASK, USER, worldHandlers } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

const PHONE_TASK = {
  ...TASK,
  recording_mode: "TELEPHONY",
  status: "IN_PROGRESS",
  allowed_transitions: ["ON_HOLD", "CANCELLED"],
  can_reassign: false,
};

function call(state: string, extra: Record<string, unknown> = {}) {
  return {
    id: "c1",
    task_id: "t1",
    provider: "TXCONTACT",
    state,
    agent_id: "70001",
    phone_hint: "10",
    moderator_id: "m1",
    moderator_name: "Mona Moderator",
    dialled_at: "2026-11-13T10:00:00Z",
    closed_at: null,
    cancel_reason: null,
    note: "",
    provider_reference: "fec72ece-df50-11f1-96b6-bc24110b2437",
    provider_session_id: null,
    recording_id: null,
    fetch_attempts: 0,
    next_fetch_at: null,
    failure_code: null,
    failure_detail: null,
    checklist: {},
    candidates: [],
    events: [
      {
        at: "2026-11-13T10:00:00Z",
        kind: "DIAL_ACCEPTED",
        actor: null,
        text: "TXCONTACT answered HTTP 200: Contact queued",
      },
    ],
    ...extra,
  };
}

describe("phone calls on the task page", () => {
  it("starts the call, ticks the checklist, then closes it, showing only the server's state", async () => {
    let calls: Record<string, unknown>[] = [];
    const api = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, PHONE_TASK],
        "GET /api/v1/tasks/t1/calls": () => [200, calls],
        "POST /api/v1/tasks/t1/calls": () => {
          calls = [call("DIALLING")];
          return [201, calls[0]];
        },
        "POST /api/v1/calls/c1/checklist": (body) => {
          const { item, done } = body as { item: string; done: boolean };
          const before = Object.entries(calls[0]?.checklist as Record<string, string>);
          const ticked = Object.fromEntries([
            ...before.filter(([k]) => k !== item),
            ...(done ? [[item, "2026-11-13T10:01:00+00:00"]] : []),
          ]);
          calls = [call("DIALLING", { checklist: ticked })];
          return [200, calls[0]];
        },
        "POST /api/v1/calls/c1/call-b": () => {
          calls = [
            call("DIALLING", {
              checklist: calls[0]?.checklist,
              b_dial_attempts: 1,
              b_dial_status: "ACCEPTED",
              b_phone_hint: "78",
              b_dialled_at: "2026-11-13T10:02:00Z",
            }),
          ];
          return [200, calls[0]];
        },
        "POST /api/v1/calls/c1/recording/start": () => {
          calls = [
            call("DIALLING", {
              ...calls[0],
              record_started_at: "2026-11-13T10:03:00Z",
              record_stopped_at: null,
            }),
          ];
          return [200, calls[0]];
        },
        "POST /api/v1/calls/c1/recording/stop": () => {
          calls = [call("DIALLING", { ...calls[0], record_stopped_at: "2026-11-13T10:15:30Z" })];
          return [200, calls[0]];
        },
        "POST /api/v1/calls/c1/close": () => {
          calls = [call("WAITING_FOR_RECORDING", { closed_at: "2026-11-13T10:20:00Z" })];
          return [200, calls[0]];
        },
      }),
    );
    renderAt("/tasks/t1");
    await userEvent.click(
      await screen.findByRole("button", { name: "Start call" }, { timeout: 5000 }),
    );
    expect(await screen.findByRole("heading", { name: "On the call" })).toBeInTheDocument();
    expect(screen.getByText("The phone system is ringing participant A")).toBeInTheDocument();
    // The provider's own answer is in the Super Admin's technical log.
    expect(screen.getByText("Technical log")).toBeInTheDocument();
    // Both people must be confirmed on the call before it can be closed.
    expect(screen.getByRole("button", { name: "Close call" })).toBeDisabled();
    // B is rung from here once A is on the line (D-111).
    const ringB = screen.getByRole("button", { name: "Call participant B" });
    expect(ringB).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: /Participant A is on the call/ }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Call participant B" })).toBeEnabled(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Call participant B" }));
    expect(
      await screen.findByText(/The phone system is ringing participant B \(number ending 78/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ring B again (2 left)" })).toBeEnabled();
    await userEvent.click(
      await screen.findByRole("checkbox", { name: /Participant B is on the call/ }),
    );
    // B is on: nothing left to ring.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /Ring B again/ })).not.toBeInTheDocument(),
    );
    // Both on the line: the conversation is marked (D-113); closing needs the start.
    expect(screen.getByRole("button", { name: "Close call" })).toBeDisabled();
    await userEvent.click(await screen.findByRole("button", { name: "Start recording" }));
    expect(await screen.findByRole("button", { name: "Stop recording" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Close call" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    expect(await screen.findByText(/Only this part is delivered/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start again" })).toBeInTheDocument();
    expect(
      api.calls.filter((c) => c.path === "/api/v1/calls/c1/checklist").map((c) => c.body),
    ).toEqual([
      { item: "A_JOINED", done: true },
      { item: "B_JOINED", done: true },
    ]);
    expect(api.calls.filter((c) => c.path === "/api/v1/calls/c1/call-b")).toHaveLength(1);
    await userEvent.type(screen.getByLabelText("Note for the record (optional)"), "clear line");
    await userEvent.click(screen.getByRole("button", { name: "Close call" }));
    expect(
      await screen.findByRole("heading", { name: "Fetching the recording" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(api.calls.find((c) => c.path === "/api/v1/calls/c1/close")?.body).toEqual({
        note: "clear line",
      }),
    );
    // While the recording is fetched the call can still be cancelled.
    expect(screen.getByRole("button", { name: "Cancel this call" })).toBeInTheDocument();
  });

  it("keeps an open cancel form and its note while the page refreshes itself", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const api = fakeApi(
        signedInAs(ALL_PERMISSIONS, {
          ...worldHandlers(),
          "GET /api/v1/tasks/t1": () => [200, PHONE_TASK],
          "GET /api/v1/tasks/t1/calls": () => [200, [call("DIALLING")]],
        }),
      );
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderAt("/tasks/t1");
      await user.click(
        await screen.findByRole("button", { name: "Cancel this call" }, { timeout: 5000 }),
      );
      const box = within(screen.getByRole("dialog", { name: "Cancel this call?" }));
      await user.selectOptions(box.getByLabelText(/^Reason/), "POOR_QUALITY");
      await user.type(box.getByLabelText(/^Note$/), "echo on the line");
      const before = api.calls.filter((c) => c.path === "/api/v1/tasks/t1/calls").length;
      await vi.advanceTimersByTimeAsync(11_000); // two refreshes
      await waitFor(() =>
        expect(api.calls.filter((c) => c.path === "/api/v1/tasks/t1/calls").length).toBeGreaterThan(
          before,
        ),
      );
      expect(box.getByLabelText(/^Note$/)).toHaveValue("echo on the line");
      expect(box.getByLabelText(/^Reason/)).toHaveValue("POOR_QUALITY");
      expect(screen.queryByText("Loading the phone call")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("says plainly when phone calls are not configured", async () => {
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, PHONE_TASK],
        "GET /api/v1/telephony/status": () => [200, { configured: false, provider: "TXCONTACT" }],
      }),
    );
    renderAt("/tasks/t1");
    expect(
      await screen.findByRole("heading", { name: "Phone calls are not set up" }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start call" })).not.toBeInTheDocument();
  });

  it("lets a person pick the right TxContact call when several fit", async () => {
    const api = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, PHONE_TASK],
        "GET /api/v1/tasks/t1/calls": () => [
          200,
          [
            call("NEEDS_MATCH", {
              failure_code: "SEVERAL_CALLS",
              failure_detail: "2 provider calls fit this call; choose the right one",
              candidates: [
                {
                  key: "k1",
                  session_id: "…10-X1",
                  start: "2026-11-13T10:01:00Z",
                  duration: "300",
                  from_hint: "10",
                  to_hint: "01",
                  file: "rec_…10-X1.wav",
                },
                {
                  key: "k2",
                  session_id: "…10-X2",
                  start: "2026-11-13T10:02:00Z",
                  duration: "290",
                  from_hint: "10",
                  to_hint: "01",
                  file: "rec_…10-X2.wav",
                },
              ],
            }),
          ],
        ],
        "POST /api/v1/calls/c1/match": () => [200, call("WAITING_FOR_RECORDING")],
      }),
    );
    renderAt("/tasks/t1");
    const choose = await screen.findAllByRole(
      "button",
      { name: "This is the call" },
      { timeout: 5000 },
    );
    expect(choose).toHaveLength(2);
    await userEvent.click(choose[1] as HTMLElement);
    await waitFor(() =>
      expect(api.calls.find((c) => c.path === "/api/v1/calls/c1/match")?.body).toEqual({
        key: "k2",
      }),
    );
  });

  it("lets the moderator listen to the call recording before sending it to QC", async () => {
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [
          200,
          { ...PHONE_TASK, status: "RECORDED", allowed_transitions: ["AUDIO_QC", "IN_PROGRESS"] },
        ],
        "GET /api/v1/tasks/t1/calls": () => [200, [call("RECORDED", { recording_id: "r1" })]],
        "GET /api/v1/tasks/t1/recordings": () => [
          200,
          [
            {
              id: "r1",
              task_id: "t1",
              state: "READY",
              saved_seconds: 42,
              assets: [
                { id: "a1", kind: "PROVIDER_ORIGINAL_MIXED", version: 1 },
                {
                  id: "a2",
                  kind: "TELEPHONY_DERIVED_PCM",
                  version: 1,
                  sample_rate: 16000,
                  channels: 1,
                  duration_ms: 36_000, // cut to the recording marks from the provider's 42 s
                },
              ],
            },
          ],
        ],
        "GET /api/v1/tasks/t1/audio-qc": () => [
          200,
          {
            task_status: "RECORDED",
            qc_user_id: null,
            qc_name: null,
            can_decide: false,
            can_assign: false,
            can_recheck: false,
            reasons: { FAIL: [] },
            results: [],
          },
        ],
      }),
    );
    renderAt("/tasks/t1");
    expect(
      await screen.findByRole("heading", { name: "Check the call recording" }, { timeout: 5000 }),
    ).toBeInTheDocument();
    // In the moderator's card and in the Recordings table: a recording under a minute is shown
    // in seconds, as one file in plain words: the delivered file's length, not the whole call's.
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: /Listen/ }).length).toBeGreaterThanOrEqual(2),
    );
    expect(screen.getByText("36 s")).toBeInTheDocument();
    expect(screen.queryByText("42 s")).not.toBeInTheDocument();
    expect(screen.getByText("16000 Hz, mono")).toBeInTheDocument();
    expect(screen.queryByText("No recording yet.")).not.toBeInTheDocument();
  });

  it("gives a moderator their phone seat", { timeout: 15000 }, async () => {
    const api = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "PUT /api/v1/users/u2/telephony-agent": (body) => [
          200,
          { user_id: "u2", telephony_agent_id: (body as { agent_id: string }).agent_id },
        ],
      }),
    );
    renderAt("/admin/users/u2");
    await userEvent.type(
      await screen.findByLabelText("Phone seat", {}, { timeout: 5000 }),
      "70001",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save phone seat" }));
    expect(await screen.findByText("Phone seat saved.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({ agent_id: "70001" });
    expect(USER.roles).toContain("MODERATOR");
  });
});

describe("phone calls in plain words (UI review 2026-11-17)", () => {
  const MODERATOR = { ...ME, roles: ["MODERATOR"], permissions: ALL_PERMISSIONS };

  it("waits for both people's consent before the recording starts, and asks for it right under the call (D-119)", async () => {
    fakeApi({
      ...signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, { ...PHONE_TASK, consent_missing: ["B"] }],
        "GET /api/v1/tasks/t1/calls": () => [
          200,
          [call("DIALLING", { checklist: { A_JOINED: "x", B_JOINED: "y" } })],
        ],
      }),
      "GET /api/v1/auth/me": () => [200, MODERATOR],
    });
    renderAt("/tasks/t1");
    const start = await screen.findByRole("button", { name: "Start recording" }, { timeout: 5000 });
    expect(start).toBeDisabled();
    expect(screen.getByText("Note both people's consent below first.")).toBeInTheDocument();
    // The consent card sits between the call card and the call history.
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    const at = (name: string) => headings.findIndex((h) => h?.includes(name));
    expect(at("On the call")).toBeLessThan(at("Consent"));
    expect(at("Consent")).toBeLessThan(at("Phone calls"));
  });

  it("tells a moderator what went wrong in plain words, without the provider's answer", async () => {
    fakeApi({
      ...signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, PHONE_TASK],
        "GET /api/v1/tasks/t1/calls": () => [
          200,
          [
            call("DIAL_FAILED", {
              failure_code: "PROVIDER_REFUSED",
              failure_detail: "TXCONTACT answered HTTP 500: boom",
              events: [
                {
                  at: "2026-11-13T10:00:00Z",
                  kind: "DIAL_FAILED",
                  actor: null,
                  text: "TXCONTACT answered HTTP 500: boom",
                },
              ],
            }),
          ],
        ],
      }),
      "GET /api/v1/auth/me": () => [200, MODERATOR],
    });
    renderAt("/tasks/t1");
    const alert = await screen.findByRole("alert", {}, { timeout: 5000 });
    expect(alert).toHaveTextContent(
      "The phone system did not place the call. Ask your admin to check the phone settings.",
    );
    expect(screen.queryByText(/HTTP 500/)).not.toBeInTheDocument();
    expect(screen.queryByText("Technical log")).not.toBeInTheDocument();
    expect(screen.queryByText(/TxContact/)).not.toBeInTheDocument();
    expect(within(alert).queryByText(/seat/)).toBeNull();
  });
});

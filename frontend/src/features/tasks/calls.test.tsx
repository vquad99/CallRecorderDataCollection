// Phone calls on a telephony task (D-101, D-103): the moderator starts the call, ticks the
// checklist and closes it; the page shows only what the server says and keeps what is typed while
// it refreshes; a call that needs a person offers the provider's calls to choose from; a call can
// be cancelled while its recording is fetched; the finished recording can be listened to; and a
// Super Admin gives a moderator their phone seat. Moderators read plain words; the provider's own
// answers are in the Super Admin's technical log; recording waits for both people's consent.
// The moderator's phone line (D-133) is signed in by the portal itself, Start call waits for it to
// be Ready, it is Ready again after each call without a second sign-in, and it goes offline at
// sign-out. Before Start call the project's reminders show with the task's own speakers, and Send
// to QC waits for both speakers' device details (D-147).
// Requirements: TEL-002, TEL-004, TEL-018, TEL-036, TEL-037, GEN-004, FTF-014
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, signedInAs, type Handler } from "../../test/fakeApi";
import { FakeAgentManager, FakeSocket } from "../../test/fakeWebSocket";
import { ALL_PERMISSIONS, DEVICE_DETAILS, TASK, USER, worldHandlers } from "../../test/world";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeSocket.reset();
});

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
  it("follows one button at a time: start, A answered, B answered, stop and close (D-127)", async () => {
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
    expect(screen.getByText(/Ringing participant A \(number ending 10\)/)).toBeInTheDocument();
    // The provider's own answer is in the Super Admin's technical log.
    expect(screen.getByText("Technical log")).toBeInTheDocument();
    // No checklist to tick: one button says what happened and does the next step.
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /A answered/ }));
    expect(
      await screen.findByText(/Ringing participant B \(number ending 78\)/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ring B again (2 left)" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: /B answered/ }));
    expect(await screen.findByRole("button", { name: "Stop and close call" })).toBeInTheDocument();
    expect(screen.getByText(/^Recording · /)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Stop and close call" }));
    expect(
      await screen.findByRole("heading", { name: "Fetching the recording" }),
    ).toBeInTheDocument();
    expect(
      api.calls.filter((c) => c.path === "/api/v1/calls/c1/checklist").map((c) => c.body),
    ).toEqual([
      { item: "A_JOINED", done: true },
      { item: "B_JOINED", done: true },
    ]);
    expect(
      api.calls
        .filter((c) => c.path.startsWith("/api/v1/calls/c1/") && c.method === "POST")
        .map((c) => c.path.replace("/api/v1/calls/c1/", "")),
    ).toEqual(["checklist", "call-b", "checklist", "recording/start", "recording/stop", "close"]);
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
              current: true,
              saved_seconds: 42,
              assets: [
                { id: "a1", kind: "PROVIDER_ORIGINAL_MIXED", version: 1 },
                {
                  id: "a2",
                  kind: "TELEPHONY_DERIVED_PCM",
                  version: 1,
                  sample_rate: 16000,
                  channels: 2, // TxContact's recordings are stereo (D-134)
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
    expect(screen.getByText("16000 Hz, stereo")).toBeInTheDocument();
    expect(screen.queryByText("No recording yet.")).not.toBeInTheDocument();
  });

  it("gives a moderator their phone seat", { timeout: 15000 }, async () => {
    const api = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "PUT /api/v1/users/u2/telephony-agent": (body) => [
          200,
          {
            user_id: "u2",
            telephony_agent_id: (body as { agent_id: string }).agent_id,
            has_password: false,
          },
        ],
      }),
    );
    renderAt("/admin/users/u2");
    await userEvent.type(
      await screen.findByLabelText("Seat number", {}, { timeout: 5000 }),
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

  it("does not call anyone before both have agreed on their consent form (D-127)", async () => {
    fakeApi({
      ...signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, { ...PHONE_TASK, consent_missing: ["B"] }],
        "GET /api/v1/tasks/t1/calls": () => [200, []],
      }),
      "GET /api/v1/auth/me": () => [200, MODERATOR],
    });
    renderAt("/tasks/t1");
    const start = await screen.findByRole("button", { name: "Start call" }, { timeout: 5000 });
    expect(start).toBeDisabled();
    expect(
      screen.getByText(/Participant B has not agreed on the consent form yet/),
    ).toBeInTheDocument();
    // Who is missing sits between the call card and the call history.
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    const at = (name: string) => headings.findIndex((h) => h?.includes(name));
    expect(at("Ready to call")).toBeLessThan(at("Waiting for consent"));
    expect(at("Waiting for consent")).toBeLessThan(at("Phone calls"));
  });

  it("reminds the moderator before Start call, with each speaker's code (D-147)", async () => {
    const reminders = {
      speaker_id: true,
      topics: ["weather", "travel"],
      avoid: ["politics"],
      tips: ["Hold the handset near the mouth and keep the loudspeaker off."],
    };
    fakeApi({
      ...signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, { ...PHONE_TASK, reminders }],
        "GET /api/v1/tasks/t1/calls": () => [200, []],
      }),
      "GET /api/v1/auth/me": () => [200, MODERATOR],
    });
    renderAt("/tasks/t1");
    await screen.findByRole("button", { name: "Start call" }, { timeout: 5000 });
    const card = screen.getByRole("region", { name: "Ready to call" });
    const lines = within(within(card).getByRole("note", { name: "Reminders" }))
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(lines).toEqual([
      "Ask each speaker to start with:“I am Asha and speaker ID P000001”“I am Bina and speaker ID P000002”",
      "“I am Asha and speaker ID P000001”",
      "“I am Bina and speaker ID P000002”",
      "Talk about: weather, travel",
      "Avoid: politics",
      "Hold the handset near the mouth and keep the loudspeaker off.",
    ]);
  });

  it(
    "keeps Send to QC waiting for both speakers' device details (D-147)",
    { timeout: 15000 },
    async () => {
      let task = {
        ...PHONE_TASK,
        status: "RECORDED",
        allowed_transitions: ["AUDIO_QC", "IN_PROGRESS"],
        device_details_missing: ["P000001", "P000002"],
      };
      const api = fakeApi({
        ...signedInAs(ALL_PERMISSIONS, {
          ...worldHandlers(),
          "GET /api/v1/tasks/t1": () => [200, task],
          "GET /api/v1/tasks/t1/calls": () => [200, [call("RECORDED", { recording_id: "r1" })]],
          "GET /api/v1/tasks/t1/device-details": () => [
            200,
            { ...DEVICE_DETAILS, call_type: "Telephonic" },
          ],
          "PUT /api/v1/tasks/t1/device-details": () => {
            task = { ...task, device_details_missing: [] };
            return [200, { ...DEVICE_DETAILS, call_type: "Telephonic", complete: true }];
          },
          "GET /api/v1/tasks/t1/audio-qc": () => [
            404,
            { error: { code: "NOT_FOUND", message: "Not found" } },
          ],
          "POST /api/v1/tasks/t1/transition": () => [200, { ...task, status: "AUDIO_QC" }],
        }),
        "GET /api/v1/auth/me": () => [200, MODERATOR],
      });
      renderAt("/tasks/t1");
      const send = await screen.findByRole("button", { name: "Send to QC" }, { timeout: 5000 });
      expect(send).toBeDisabled();
      expect(send).toHaveAccessibleDescription(
        "Fill in the device details of P000001 and P000002 first (Device details card).",
      );
      // The card sits under the call card, before the call history.
      const card = await screen.findByRole("region", { name: "Device details" });
      expect(await within(card).findByText(/Call type: Telephonic/)).toBeInTheDocument();
      const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
      expect(headings.indexOf("Device details")).toBeGreaterThan(
        headings.indexOf("Check the call recording"),
      );
      expect(headings.indexOf("Device details")).toBeLessThan(headings.indexOf("Phone calls"));
      for (const side of ["A", "B"]) {
        const who = within(card).getByRole("group", { name: new RegExp(`^Participant ${side}`) });
        await userEvent.type(within(who).getByLabelText("Device make"), "Nokia");
        await userEvent.type(within(who).getByLabelText("Device model"), "105");
        for (const question of [
          "Bluetooth earphones used",
          "Wired earphones used",
          "Loudspeaker on",
        ])
          await userEvent.click(
            within(within(who).getByRole("group", { name: question })).getByRole("radio", {
              name: "No",
            }),
          );
      }
      await userEvent.click(within(card).getByRole("button", { name: "Save device details" }));
      await waitFor(() => expect(screen.getByRole("button", { name: "Send to QC" })).toBeEnabled());
      await userEvent.click(screen.getByRole("button", { name: "Send to QC" }));
      await waitFor(() =>
        expect(api.calls.find((c) => c.path.endsWith("/transition"))?.body).toMatchObject({
          to: "AUDIO_QC",
        }),
      );
    },
  );

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

describe("the moderator's phone line (D-133)", () => {
  const SEAT = {
    url: "wss://agents.example.org/txagentmanager/",
    tenant_id: "desicrew",
    agent_id: "70001",
    extension: "70001",
    has_password: true,
  };
  const WITH_SEAT = {
    ...ME,
    roles: ["MODERATOR"],
    permissions: ALL_PERMISSIONS,
    telephony_agent_id: "70001",
    telephony_has_password: true,
  };

  /** A moderator with a phone seat on the phone task; TxContact's agent manager answers. */
  function line(extra: Record<string, Handler> = {}, me: Record<string, unknown> = WITH_SEAT) {
    const manager = new FakeAgentManager();
    FakeSocket.reset(manager);
    vi.stubGlobal("WebSocket", FakeSocket);
    const api = fakeApi({
      ...signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, PHONE_TASK],
        "GET /api/v1/tasks/t1/calls": () => [200, []],
        "GET /api/v1/telephony/status": () => [
          200,
          { configured: true, provider: "TXCONTACT", seat_login: SEAT },
        ],
        "GET /api/v1/auth/phone-seat/password": () => [200, { password: "seat-pass" }],
        "POST /api/v1/auth/logout": () => [204, null],
        ...extra,
      }),
      "GET /api/v1/auth/me": () => [200, me],
    });
    renderAt("/tasks/t1");
    return { manager, api };
  }

  it("is Ready without a click, and two calls in a row need no second sign-in", async () => {
    let calls: Record<string, unknown>[] = [];
    const cancel =
      (id: string): Handler =>
      () => {
        calls = calls.map((c) =>
          c.id === id ? call("CANCELLED", { id, cancel_reason: "NO_ANSWER" }) : c,
        );
        return [200, calls[0]];
      };
    const { manager, api } = line({
      "GET /api/v1/tasks/t1/calls": () => [200, calls],
      "POST /api/v1/tasks/t1/calls": () => {
        calls = [call("DIALLING", { id: `c${calls.length + 1}` }), ...calls];
        manager.change("ON_CALL"); // the call reaches the seat
        return [201, calls[0]];
      },
      "POST /api/v1/calls/c1/cancel": cancel("c1"),
      "POST /api/v1/calls/c2/cancel": cancel("c2"),
    });
    expect(await screen.findByText("Phone line: Ready", {}, { timeout: 5000 })).toBeInTheDocument();
    for (const n of [1, 2]) {
      const start = await screen.findByRole("button", { name: "Start call" });
      await waitFor(() => expect(start).toBeEnabled());
      await userEvent.click(start);
      expect(await screen.findByText("Phone line: On a call")).toBeInTheDocument();
      await userEvent.click(await screen.findByRole("button", { name: "Cancel this call" }));
      const box = within(screen.getByRole("dialog", { name: "Cancel this call?" }));
      await userEvent.selectOptions(box.getByLabelText(/^Reason/), "NO_ANSWER");
      await userEvent.click(box.getByRole("button", { name: "Cancel the call" }));
      // Over in the portal: the seat is made Ready again for the next call.
      expect(await screen.findByText("Phone line: Ready")).toBeInTheDocument();
      expect(calls).toHaveLength(n);
    }
    expect(FakeSocket.sockets).toHaveLength(1);
    expect(FakeSocket.names().filter((e) => e === "CONNECT" || e === "LOGIN")).toEqual([
      "CONNECT",
      "LOGIN",
    ]);
    // The password was taken once, for the sign-in, and is kept nowhere in the browser.
    expect(api.calls.filter((c) => c.path.startsWith("/api/v1/auth/phone-seat"))).toEqual([
      { method: "GET", path: "/api/v1/auth/phone-seat/password?purpose=line", body: undefined },
    ]);
    expect(localStorage.length + sessionStorage.length).toBe(0);
  });

  it("says why the line is not connected, keeps Start call waiting, and tries again", async () => {
    let password = "old-pass";
    line({ "GET /api/v1/auth/phone-seat/password": () => [200, { password }] });
    expect(
      await screen.findByText(
        "Phone line not connected: Invalid agent credentials",
        {},
        { timeout: 5000 },
      ),
    ).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Start call" })).toBeDisabled();
    expect(
      screen.getByText("Your phone line is not connected. Click Try again at the top of the page."),
    ).toBeInTheDocument();
    password = "seat-pass"; // the admin saved the right one
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Phone line: Ready")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Start call" })).toBeEnabled());
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("asks a moderator without a saved seat password to ask their admin; nothing connects", async () => {
    line(
      {
        "GET /api/v1/telephony/status": () => [
          200,
          { configured: true, provider: "TXCONTACT", seat_login: { ...SEAT, has_password: false } },
        ],
      },
      { ...WITH_SEAT, telephony_has_password: false },
    );
    expect(
      await screen.findByText(
        "Ask your admin to save your phone seat password.",
        {},
        { timeout: 5000 },
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start call" })).toBeDisabled();
    expect(screen.queryByText(/Phone line/)).not.toBeInTheDocument();
    expect(FakeSocket.sockets).toHaveLength(0);
  });

  it("takes the line offline when the moderator signs out", async () => {
    const { manager } = line();
    expect(await screen.findByText("Phone line: Ready", {}, { timeout: 5000 })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() =>
      expect(FakeSocket.names().slice(-3)).toEqual(["CHANGE_AGENT_STATE", "LOGOUT", "DISCONNECT"]),
    );
    expect(FakeSocket.sockets[0]?.sent.at(-3)?.DATA).toEqual({
      STATE: "OFFLINE",
      EXTENSION: "70001",
    });
    expect(manager.state).toBe("OFFLINE");
  });

  it("shows a Super Admin with a seat what the line sent and received, never the password", async () => {
    line({}, { ...WITH_SEAT, roles: ["SUPER_ADMIN"] });
    expect(await screen.findByText("Phone line: Ready", {}, { timeout: 5000 })).toBeInTheDocument();
    const log = await screen.findByText("Phone line log (this browser)");
    await userEvent.click(log);
    const details = log.closest("details") as HTMLElement;
    expect(details).toHaveTextContent('"EVENT_NAME":"LOGIN"');
    expect(details).not.toHaveTextContent("seat-pass");
  });
});

// Phone calls on a telephony task (D-101): the moderator starts and closes the call, the page shows
// only what the server says, a call that needs a person offers the provider's calls to choose from,
// and a Super Admin gives a moderator their TxContact agent seat.
// Requirements: TEL-002, TEL-018, TEL-036, TEL-037, GEN-004
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, TASK, USER, worldHandlers } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

const PHONE_TASK = {
  ...TASK,
  recording_mode: "TELEPHONY",
  status: "IN_PROGRESS",
  allowed_transitions: ["ON_HOLD", "CANCELLED"],
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
    provider_session_id: null,
    recording_id: null,
    fetch_attempts: 0,
    next_fetch_at: null,
    failure_code: null,
    failure_detail: null,
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
  it("starts the call, then closes it, showing only the server's state", async () => {
    let calls: unknown[] = [];
    const api = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, PHONE_TASK],
        "GET /api/v1/tasks/t1/calls": () => [200, calls],
        "POST /api/v1/tasks/t1/calls": () => {
          calls = [call("DIALLING")];
          return [201, calls[0]];
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
    expect(screen.getAllByText(/Contact queued/).length).toBeGreaterThan(0);
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
                  session_id: "X1",
                  start: "2026-11-13T10:01:00Z",
                  duration: "300",
                  from_hint: "10",
                  to_hint: "01",
                  file: "rec_X1.wav",
                },
                {
                  session_id: "X2",
                  start: "2026-11-13T10:02:00Z",
                  duration: "290",
                  from_hint: "10",
                  to_hint: "01",
                  file: "rec_X2.wav",
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
        session_id: "X2",
      }),
    );
  });

  it("gives a moderator their TxContact agent seat", { timeout: 15000 }, async () => {
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
      await screen.findByLabelText("TxContact agent seat", {}, { timeout: 5000 }),
      "70001",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save agent seat" }));
    expect(await screen.findByText("Agent seat saved.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({ agent_id: "70001" });
    expect(USER.roles).toContain("MODERATOR");
  });
});

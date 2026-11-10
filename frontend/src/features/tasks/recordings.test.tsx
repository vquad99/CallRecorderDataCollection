// The task page lists finished recordings; a download brings the consent record with the audio
// (D-068). Requirements: PART-015, STOR-006
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, TASK, worldHandlers } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

const RECORDING = {
  id: "r1",
  task_id: "t1",
  state: "READY",
  saved_seconds: 600,
  assets: [
    { id: "a1", kind: "BROWSER_ORIGINAL" },
    { id: "a2", kind: "FTF_DERIVED_PCM" },
  ],
};

function open(permissions: string[]) {
  vi.stubGlobal(
    "URL",
    Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => {} }),
  );
  return fakeApi(
    signedInAs(permissions, {
      ...worldHandlers(),
      "GET /api/v1/tasks/t1": () => [200, { ...TASK, status: "RECORDED" }],
      "GET /api/v1/tasks/t1/recordings": () => [200, [RECORDING]],
      "POST /api/v1/assets/a2/url": () => [
        200,
        { url: "https://storage.example/a2.wav", expires_in: 300 },
      ],
      "GET /api/v1/recordings/r1/consent-form": () => [200, "<html></html>"],
    }),
  );
}

describe("recordings on the task page", () => {
  it("downloads the delivery file and the consent record together", async () => {
    const { calls } = open(ALL_PERMISSIONS);
    renderAt("/tasks/t1");
    await userEvent.click(
      await screen.findByRole("button", { name: "Download with consent form" }),
    );
    expect(await screen.findByText("Recording and consent record downloaded.")).toBeInTheDocument();
    await waitFor(() => {
      expect(calls.find((c) => c.path === "/api/v1/assets/a2/url")?.body).toEqual({
        purpose: "download",
      });
      expect(calls.some((c) => c.path === "/api/v1/recordings/r1/consent-form")).toBe(true);
    });
  });

  it("offers no download without the download right", async () => {
    open(ALL_PERMISSIONS.filter((p) => p !== "recordings.download"));
    renderAt("/tasks/t1");
    expect(await screen.findByText(/audio \+ consent record/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download with consent form" })).toBeNull();
  });
});

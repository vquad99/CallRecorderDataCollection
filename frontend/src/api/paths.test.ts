// Requirements: SEC-007, FND-016
// Ids from the address bar are encoded into API paths (security audit 2026-11-23, D-160): a link
// like /tasks/new?project=../users?x= must not make the page call another part of the API.
import { afterEach, describe, expect, it, vi } from "vitest";

import { seg } from "./client";
import { getProject, listExports, listMembers } from "./projects";
import { getTask } from "./work";

const ok = () =>
  new Response("{}", { status: 200, headers: { "content-type": "application/json" } });

afterEach(() => vi.unstubAllGlobals());

describe("API paths", () => {
  it("encodes a path segment so it stays one segment", () => {
    expect(seg("../users?x=")).toBe("..%2Fusers%3Fx%3D");
    expect(seg("a/b#c")).toBe("a%2Fb%23c");
    expect(seg("6f1c2d3e-0000-4000-8000-000000000001")).toBe(
      "6f1c2d3e-0000-4000-8000-000000000001",
    );
  });

  it("keeps an id taken from a link inside its own segment", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(ok()));
    vi.stubGlobal("fetch", fetchMock);
    const crafted = "1e1b666f-0000-4000-8000-000000000000/export?content=participants&format=csv#";
    await getProject(crafted);
    await listMembers("../../v1/auth/sessions#");
    await listExports("..%2Fusers");
    await getTask("../users");
    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(urls).toEqual([
      "/api/v1/projects/1e1b666f-0000-4000-8000-000000000000%2Fexport%3Fcontent%3Dparticipants%26format%3Dcsv%23",
      "/api/v1/projects/..%2F..%2Fv1%2Fauth%2Fsessions%23/members",
      "/api/v1/projects/..%252Fusers/exports?page_size=20",
      "/api/v1/tasks/..%2Fusers",
    ]);
  });
});

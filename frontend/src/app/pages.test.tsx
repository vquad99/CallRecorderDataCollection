// Every page in every state (owner's test list, Option C).
// Requirements: FND-015, FND-018, FND-019, FND-020, ROLE-011, AUTH-016
//
// 1. Inventory: every route in routes.tsx has an entry below, so a new page cannot ship untested.
// 2. Loaded: the page shows its content and has no accessibility violations.
// 3. Loading: a polite status message is shown while the data is on its way.
// 4. Failed: for a server error, not found, no permission, service not configured and a lost
//    connection, the page says what happened (with the server's reference for a server error) and
//    "Try again" loads it once the problem is gone.
// 5. Guards: without the page's permission the user sees "No access"; signed out, the user is sent
//    to sign-in and the address is kept.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs, type Handler } from "../test/fakeApi";
import { BY_PATH, FLAT, PAGES, type PageSpec } from "../test/pageSpecs";
import { ALL_PERMISSIONS, worldHandlers } from "../test/world";

afterEach(() => vi.unstubAllGlobals());

const SIGNED_OUT: Record<string, Handler> = {
  "GET /api/v1/auth/csrf": () => [204, null],
  "GET /api/v1/auth/me": () => [401, { error: { code: "UNAUTHENTICATED", message: "Sign in" } }],
};

function open(spec: PageSpec, overrides: Record<string, Handler> = {}, perms = ALL_PERMISSIONS) {
  const handlers = { ...worldHandlers(), ...overrides };
  fakeApi(spec.anonymous ? { ...handlers, ...SIGNED_OUT } : signedInAs(perms, handlers));
  return renderAt(spec.url);
}

const loaded = (spec: PageSpec) => screen.findAllByText(spec.shows, {}, { timeout: 3000 });

describe("page inventory", () => {
  it("has an entry for every route", () => {
    expect(Object.keys(PAGES).sort()).toEqual(FLAT.map((r) => r.path).sort());
  });
});

const ALL = Object.entries(PAGES);
const WITH_DATA = ALL.filter(([, s]) => s.data);

describe.each(ALL)("%s", (_, spec) => {
  it("shows its content with no accessibility violations", async () => {
    open(spec);
    await loaded(spec);
    const result = await axe.run(document.body, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(result.violations.map((v) => `${v.id}: ${v.nodes[0]?.html ?? ""}`)).toEqual([]);
  });
});

const FAILURES: [string, Handler, RegExp][] = [
  [
    "server error",
    () => [
      500,
      {
        error: { code: "INTERNAL_ERROR", message: "Internal server error", request_id: "req-500" },
      },
    ],
    /req-500/,
  ],
  [
    "not found",
    () => [404, { error: { code: "NOT_FOUND", message: "Item not found" } }],
    /Item not found/,
  ],
  [
    "no permission",
    () => [403, { error: { code: "FORBIDDEN", message: "You do not have permission to do this" } }],
    /do not have permission/,
  ],
  [
    "service not configured",
    () => [503, { error: { code: "NOT_CONFIGURED", message: "Storage is not configured" } }],
    /not configured/,
  ],
  ["lost connection", () => "NETWORK", /Cannot reach the server/],
];

describe.each(WITH_DATA)("%s while loading and after a failure", (_, spec) => {
  const key = spec.data ?? "";

  it("says it is loading until the data arrives", async () => {
    let release: (() => void) | null = null;
    const real = worldHandlers()[key];
    open(spec, {
      [key]: (body, url) =>
        new Promise((resolve) => {
          release = () => resolve(real ? real(body, url) : [200, {}]);
        }) as ReturnType<Handler>,
    });
    await waitFor(() => expect(release).not.toBeNull()); // the page's own request is pending
    const statuses = screen.getAllByRole("status").map((el) => el.textContent ?? "");
    expect(statuses.some((t) => /Loading|Checking/.test(t))).toBe(true);
    (release as unknown as () => void)();
    await loaded(spec);
  });

  it.each(FAILURES.filter(([kind]) => !spec.normal?.includes(kind)))(
    "reports a %s and recovers with Try again",
    async (_kind, fail, says) => {
      let broken = true;
      const real = worldHandlers()[key];
      open(spec, {
        [key]: (body, url) => (broken ? fail(body, url) : real ? real(body, url) : [200, {}]),
      });
      const alert = await screen.findByRole("alert", {}, { timeout: 3000 });
      await waitFor(() => expect(alert).toHaveTextContent(says));
      broken = false;
      await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
      await loaded(spec);
    },
  );
});

const GUARDED = ALL.filter(([path]) => BY_PATH.get(path)?.permission);
describe.each(GUARDED)("%s without its permission", (path, spec) => {
  it("shows No access", async () => {
    const needed = BY_PATH.get(path)?.permission;
    open(
      spec,
      {},
      ALL_PERMISSIONS.filter((p) => p !== needed),
    );
    expect(await screen.findByRole("heading", { name: "No access" })).toBeInTheDocument();
  });
});

const SIGNED_IN_ONLY = ALL.filter(([path]) => BY_PATH.get(path)?.auth);
describe.each(SIGNED_IN_ONLY)("%s when signed out", (_, spec) => {
  it("goes to sign-in and keeps the address", async () => {
    fakeApi({ ...worldHandlers(), ...SIGNED_OUT });
    const router = renderAt(spec.url);
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe(spec.url);
  });
});

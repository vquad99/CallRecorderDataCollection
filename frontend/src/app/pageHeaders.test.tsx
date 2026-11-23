// Requirements: FND-015, FND-019
// Every page in the side menu starts the same way (D-161): its title, a short line under it and its
// buttons on the right, in a title row of one height, so moving between pages nothing jumps.
import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../test/fakeApi";
import { PAGES } from "../test/pageSpecs";
import { ALL_PERMISSIONS, worldHandlers } from "../test/world";

afterEach(() => vi.unstubAllGlobals());

const MENU = [
  "/dashboard",
  "/projects",
  "/tasks",
  "/calls",
  "/participants",
  "/admin/users",
  "/admin/settings",
  "/payments",
  "/admin/audit",
  "/status",
  "/account",
];

describe.each(MENU)("%s", (path) => {
  it("has the title row every page has: the title with a short line under it", async () => {
    const spec = PAGES[path];
    if (!spec) throw new Error(`No page spec for ${path}`);
    fakeApi(signedInAs(ALL_PERMISSIONS, worldHandlers()));
    renderAt(spec.url);
    await screen.findAllByText(spec.shows, {}, { timeout: 3000 });
    const title = screen.getByRole("heading", { level: 1 });
    const text = title.parentElement;
    expect(text).toHaveClass("page-header__text");
    expect(text?.parentElement).toHaveClass("page-header");
    const lead = text?.querySelector(".page-header__lead");
    expect(lead?.textContent?.trim()).toBeTruthy();
    // One short line: it fits beside the page's buttons on a laptop screen.
    expect(lead?.textContent?.length ?? 0).toBeLessThanOrEqual(100);
  });
});

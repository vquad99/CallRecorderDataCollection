// Requirements: FND-015, FND-017, FND-023
import { beforeEach, describe, expect, it, vi } from "vitest";

import { isStaleBuildError, loadFresh, reloadOnce } from "./staleBuild";

const stale = new TypeError(
  "Failed to fetch dynamically imported module: https://dubdesk.live/assets/ParticipantsTab-old.js",
);

beforeEach(() => window.sessionStorage.clear());

describe("a page opened before an update (D-089)", () => {
  it("recognises the old-version file errors of each browser and nothing else", () => {
    expect(isStaleBuildError(stale)).toBe(true);
    expect(isStaleBuildError(new TypeError("Importing a module script failed."))).toBe(true);
    expect(isStaleBuildError(new Error("error loading dynamically imported module"))).toBe(true);
    expect(isStaleBuildError(new Error("Unable to preload CSS for /assets/x.css"))).toBe(true);
    expect(isStaleBuildError(new TypeError("Failed to fetch"))).toBe(false);
    expect(isStaleBuildError(new Error("Cannot read properties of undefined"))).toBe(false);
  });

  it("reloads once instead of failing, and shows the error if it happens again at once", async () => {
    const reload = vi.fn();
    let settled = false;
    void loadFresh(() => Promise.reject(stale), reload).then(() => {
      settled = true;
    });
    await Promise.resolve();
    await Promise.resolve();
    expect(reload).toHaveBeenCalledTimes(1);
    expect(settled).toBe(false); // keeps showing "Loading page" while the page reloads
    await expect(loadFresh(() => Promise.reject(stale), reload)).rejects.toBe(stale);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("passes other errors and good loads through untouched", async () => {
    const reload = vi.fn();
    const other = new Error("boom");
    await expect(loadFresh(() => Promise.reject(other), reload)).rejects.toBe(other);
    await expect(loadFresh(() => Promise.resolve(42), reload)).resolves.toBe(42);
    expect(reload).not.toHaveBeenCalled();
  });

  it("allows another reload once the quiet time has passed", () => {
    const reload = vi.fn();
    expect(reloadOnce(reload, 1_000_000)).toBe(true);
    expect(reloadOnce(reload, 1_010_000)).toBe(false);
    expect(reloadOnce(reload, 1_040_001)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });
});

// The installable application (D-110): manifest and icons, what the service worker keeps and
// what it never touches, the offer of a new version, installing from the account page.
// Requirements: PWA-001, PWA-002, PWA-004, PWA-005, PWA-006, PWA-007, PWA-009
import { readFileSync } from "node:fs";

import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../test/fakeApi";
import { ALL_PERMISSIONS, worldHandlers } from "../test/world";
import { InstallCard } from "./InstallCard";
import { clearInstallOffer, watchInstallOffer } from "./install";
import { registerServiceWorker } from "./register";

afterEach(() => {
  vi.unstubAllGlobals();
  document.getElementById("pwa-update")?.remove();
  clearInstallOffer();
});

describe("web app manifest", () => {
  it("names the application, opens it in its own window, and has icons of the sizes it says", () => {
    const manifest = JSON.parse(readFileSync("public/manifest.webmanifest", "utf8")) as {
      name: string;
      short_name: string;
      display: string;
      start_url: string;
      scope: string;
      theme_color: string;
      background_color: string;
      icons: { src: string; sizes: string; type: string; purpose: string }[];
    };
    expect(manifest.name).toBe("Conversation Collection");
    expect(manifest.short_name.length).toBeLessThanOrEqual(15);
    expect([manifest.display, manifest.start_url, manifest.scope]).toEqual([
      "standalone",
      "/",
      "/",
    ]);
    // The colour of the top bar, as in the page's own theme-color.
    expect(readFileSync("index.html", "utf8")).toContain(
      `<meta name="theme-color" content="${manifest.theme_color}" />`,
    );
    expect(readFileSync("index.html", "utf8")).toContain(
      '<link rel="manifest" href="/manifest.webmanifest" />',
    );
    expect(manifest.icons.map((i) => i.purpose).sort()).toEqual(["any", "any", "maskable"]);
    for (const icon of manifest.icons) {
      const png = readFileSync(`public${icon.src}`);
      expect(png.subarray(1, 4).toString(), icon.src).toBe("PNG");
      // Width and height are in the first block of a PNG file.
      expect(`${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`, icon.src).toBe(icon.sizes);
      expect(icon.type).toBe("image/png");
    }
  });
});

/** The service worker's text run against stand-ins for the browser's parts. */
function worker(online = true) {
  const listeners: Record<string, (event: never) => void> = {};
  const stores = new Map<string, Map<string, string>>();
  const fetched: string[] = [];
  const open = (name: string) => {
    if (!stores.has(name)) stores.set(name, new Map());
    const store = stores.get(name) as Map<string, string>;
    return Promise.resolve({
      addAll: (paths: string[]) => {
        paths.forEach((p) => store.set(p, `kept ${p}`));
        return Promise.resolve();
      },
      match: (request: { url: string }) => {
        const body = store.get(new URL(request.url).pathname);
        return Promise.resolve(body === undefined ? undefined : { body, ok: true });
      },
      put: (request: { url: string }, response: { body: string }) => {
        store.set(new URL(request.url).pathname, response.body);
        return Promise.resolve();
      },
    });
  };
  const caches = {
    open,
    keys: () => Promise.resolve([...stores.keys()]),
    delete: (name: string) => Promise.resolve(stores.delete(name)),
    match: (key: string | { url: string }) => {
      const path = typeof key === "string" ? key : new URL(key.url).pathname;
      for (const store of stores.values()) {
        const body = store.get(path);
        if (body !== undefined) return Promise.resolve({ body, ok: true });
      }
      return Promise.resolve(undefined);
    },
  };
  const self = {
    location: { origin: "https://app.example" },
    addEventListener: (type: string, listener: (event: never) => void) => {
      listeners[type] = listener;
    },
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn(() => Promise.resolve()) },
  };
  const fetch = (request: { url: string }) => {
    fetched.push(new URL(request.url).pathname);
    if (!online) return Promise.reject(new TypeError("offline"));
    const body = `fresh ${new URL(request.url).pathname}`;
    return Promise.resolve({ ok: true, body, clone: () => ({ body }) });
  };
  const source = readFileSync("pwa/sw.template.js", "utf8");
  new Function("self", "caches", "fetch", "Response", "URL", "BUILD", source)(
    self,
    caches,
    fetch,
    { error: () => ({ body: "error" }) },
    URL,
    "build1",
  );
  /** What the worker answers for a request, or null when it leaves the request alone. */
  const ask = async (path: string, init: { method?: string; mode?: string } = {}) => {
    let answer: Promise<{ body: string }> | null = null;
    const url = path.startsWith("http") ? path : `https://app.example${path}`;
    listeners.fetch?.({
      request: { url, method: init.method ?? "GET", mode: init.mode ?? "cors" },
      respondWith: (p: Promise<{ body: string }>) => {
        answer = p;
      },
    } as never);
    return answer === null ? null : (await (answer as Promise<{ body: string }>)).body;
  };
  const run = async (type: "install" | "activate") => {
    let done: Promise<unknown> = Promise.resolve();
    listeners[type]?.({ waitUntil: (p: Promise<unknown>) => (done = p) } as never);
    await done;
  };
  return { ask, run, stores, fetched, self, listeners };
}

describe("service worker", () => {
  it("keeps built files and the offline page, and never touches the API or other addresses", async () => {
    const sw = worker();
    await sw.run("install");
    expect([...(sw.stores.get("ccp-static-build1")?.keys() ?? [])]).toEqual([
      "/offline.html",
      "/offline.css",
      "/icon-192.png",
      "/favicon.svg",
    ]);
    // Left alone: the API, health checks, anything that changes something, other addresses.
    expect(await sw.ask("/api/v1/tasks")).toBeNull();
    expect(await sw.ask("/api/v1/recordings/r1/metadata")).toBeNull();
    expect(await sw.ask("/health/live")).toBeNull();
    expect(await sw.ask("/assets/app.js", { method: "POST" })).toBeNull();
    expect(await sw.ask("https://storage.example/recording.wav")).toBeNull();
    expect(await sw.ask("/robots.txt")).toBeNull();
    expect(sw.fetched).toEqual([]);
    // A built file: fetched once, then from the store.
    expect(await sw.ask("/assets/app-abc123.js")).toBe("fresh /assets/app-abc123.js");
    expect(await sw.ask("/assets/app-abc123.js")).toBe("fresh /assets/app-abc123.js");
    expect(sw.fetched).toEqual(["/assets/app-abc123.js"]);
    // A page: always the server's, never a kept copy.
    expect(await sw.ask("/projects", { mode: "navigate" })).toBe("fresh /projects");
    expect(sw.stores.get("ccp-static-build1")?.has("/projects")).toBe(false);
    expect([...sw.stores.keys()]).toEqual(["ccp-static-build1"]);
  });

  it("answers a page with the offline page when there is no connection", async () => {
    const sw = worker(false);
    await sw.run("install");
    expect(await sw.ask("/tasks/t1", { mode: "navigate" })).toBe("kept /offline.html");
    expect(await sw.ask("/offline.css")).toBe("kept /offline.css");
    // The API is still left alone: the page sees the failure and says so itself.
    expect(await sw.ask("/api/v1/tasks")).toBeNull();
  });

  it("drops the stores of older versions and takes over only when asked", async () => {
    const sw = worker();
    sw.stores.set("ccp-static-older", new Map([["/assets/old.js", "old"]]));
    sw.stores.set("something-else", new Map());
    await sw.run("install");
    expect(sw.self.skipWaiting).not.toHaveBeenCalled();
    await sw.run("activate");
    expect([...sw.stores.keys()].sort()).toEqual(["ccp-static-build1", "something-else"]);
    sw.listeners.message?.({ data: "something" } as never);
    expect(sw.self.skipWaiting).not.toHaveBeenCalled();
    sw.listeners.message?.({ data: "skip-waiting" } as never);
    expect(sw.self.skipWaiting).toHaveBeenCalledTimes(1);
  });
});

function container(controller: object | null) {
  const target = new EventTarget();
  const registration = Object.assign(new EventTarget(), {
    waiting: null as unknown,
    installing: null as unknown,
    update: vi.fn(() => Promise.resolve()),
  });
  const fake = Object.assign(target, {
    controller,
    register: vi.fn(() => Promise.resolve(registration)),
  });
  return { fake: fake as unknown as ServiceWorkerContainer, registration, target };
}

function newWorker(state: string) {
  return Object.assign(new EventTarget(), { state, postMessage: vi.fn() });
}

describe("a new version", () => {
  it("is offered, and the page reloads only after the person asks for it", async () => {
    const { fake, registration, target } = container({});
    const reload = vi.fn();
    registerServiceWorker(fake, reload);
    await act(async () => {});
    expect(document.getElementById("pwa-update")).toBeNull();

    const fresh = newWorker("installing");
    registration.installing = fresh;
    registration.dispatchEvent(new Event("updatefound"));
    expect(document.getElementById("pwa-update")).toBeNull(); // not ready yet
    fresh.state = "installed";
    fresh.dispatchEvent(new Event("statechange"));
    const bar = screen.getByRole("status");
    expect(bar).toHaveTextContent("A new version of the application is ready.");
    expect(bar).toHaveTextContent("not in the middle of a recording");

    // A worker taking over without the person's click (for example in another tab) reloads
    // nothing here.
    target.dispatchEvent(new Event("controllerchange"));
    expect(reload).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(fresh.postMessage).toHaveBeenCalledWith("skip-waiting");
    target.dispatchEvent(new Event("controllerchange"));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("is not announced on a first visit, and can be put off", async () => {
    // First visit: no worker is in charge yet, so the one that installs is not "new".
    const first = container(null);
    registerServiceWorker(first.fake, vi.fn());
    await act(async () => {});
    const worker = newWorker("installed");
    first.registration.installing = worker;
    first.registration.dispatchEvent(new Event("updatefound"));
    expect(document.getElementById("pwa-update")).toBeNull();

    // A version that was already waiting when the page opened is offered at once.
    const later = container({});
    later.registration.waiting = newWorker("installed");
    registerServiceWorker(later.fake, vi.fn());
    await act(async () => {});
    await userEvent.click(await screen.findByRole("button", { name: "Later" }));
    expect(document.getElementById("pwa-update")).toBeNull();
  });
});

describe("signing out", () => {
  it("leaves nothing about the person on the device (PWA-007)", async () => {
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "POST /api/v1/auth/logout": () => [204, null],
      }),
    );
    renderAt("/account");
    expect(
      await screen.findByRole("heading", { name: "My account" }, { timeout: 5000 }),
    ).toBeInTheDocument();
    // Signed in: the person's name is on the page, and still nothing is written to the device.
    expect(screen.getAllByText("Ada Admin").length).toBeGreaterThan(0);
    const stored = () =>
      [...Object.entries(window.localStorage), ...Object.entries(window.sessionStorage)]
        .map(([key, value]) => `${key}=${String(value)}`)
        .join(" ");
    expect(stored()).not.toMatch(/Ada|admin@example\.org|token|session/i);
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByText("Ada Admin")).toBeNull();
    expect(Object.keys(window.localStorage)).toEqual([]);
    expect(stored()).not.toMatch(/Ada|admin@example\.org|token|session/i);
  });
});

describe("install the application", () => {
  it("uses the browser's offer when there is one", async () => {
    watchInstallOffer();
    render(<InstallCard />);
    expect(screen.getByText(/has not offered to install it on this page/)).toBeInTheDocument();
    expect(screen.getByText(/Safari on an iPhone or iPad/)).toBeInTheDocument();

    const prompt = vi.fn(() => Promise.resolve());
    const offer = Object.assign(new Event("beforeinstallprompt", { cancelable: true }), {
      prompt,
      userChoice: Promise.resolve({ outcome: "accepted" as const }),
    });
    act(() => {
      window.dispatchEvent(offer);
    });
    expect(offer.defaultPrevented).toBe(true); // the application shows its own button
    await userEvent.click(screen.getByRole("button", { name: "Install" }));
    expect(prompt).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/Installed\. Look for Conversation Collection/)).toBeVisible();
    // The offer can be used once.
    expect(screen.queryByRole("button", { name: "Install" })).toBeNull();
  });

  it("says so in the installed application", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("standalone") }));
    render(<InstallCard />);
    expect(screen.getByRole("heading", { name: "Installed application" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Install" })).toBeNull();
  });
});

// Test-only helpers: a fake backend for fetch, and rendering the real app routes at a path.
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";

import { routes } from "../app/routes";
import { AuthProvider } from "../auth/AuthContext";

type Reply = [number, unknown] | [number, unknown, Record<string, string>];

/** A reply, a delayed reply, or "NETWORK" to make the request fail as if the connection dropped. */
export type Handler = (body: unknown, url: URL) => Reply | "NETWORK" | Promise<Reply | "NETWORK">;

export function json(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

export function fakeApi(handlers: Record<string, Handler>) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
    const url = new URL(input, "http://localhost");
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    calls.push({ method, path: url.pathname + url.search, body });
    const handler = handlers[`${method} ${url.pathname}`];
    if (!handler)
      return json(404, { error: { code: "NOT_FOUND", message: "Not found", request_id: "t" } });
    const reply = await handler(body, url);
    if (reply === "NETWORK") throw new TypeError("Failed to fetch");
    const [status, payload, headers] = reply;
    return status === 204 ? new Response(null, { status }) : json(status, payload, headers ?? {});
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export const ME = {
  id: "u1",
  email: "admin@example.org",
  display_name: "Ada Admin",
  roles: ["SUPER_ADMIN"],
  permissions: [
    "projects.view",
    "projects.create",
    "projects.manage",
    "projects.members",
    "users.manage",
    "settings.manage",
  ],
  project_ids: [],
  mfa_enabled: false,
};

export function signedInAs(permissions: string[], extra: Record<string, Handler> = {}) {
  return {
    "GET /api/v1/auth/csrf": (() => [204, null]) as Handler,
    "GET /api/v1/auth/me": (() => [200, { ...ME, permissions }]) as Handler,
    ...extra,
  };
}

export function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>,
  );
  return router;
}

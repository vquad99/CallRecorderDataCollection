// Test-only: the page list shared by the page and navigation tests (Option C). Every route in
// routes.tsx needs an entry; tests/app/pages.test.tsx fails when one is missing.
import { isValidElement, type ReactElement } from "react";
import type { RouteObject } from "react-router";

import { routes } from "../app/routes";
import { RequireAuth, RequirePermission } from "../auth/guards";

export interface PageSpec {
  url: string;
  /** Failure kinds that are a normal answer for this page's request (not an error). */
  normal?: string[];
  shows: RegExp; // text that appears only once the page's data is loaded
  data?: string; // the request whose failure the page must report
  anonymous?: boolean; // a page for signed-out visitors
}

export const PAGES: Record<string, PageSpec> = {
  "/login": { url: "/login", shows: /^Sign in$/, anonymous: true },
  "/forgot-password": { url: "/forgot-password", shows: /Reset your password/, anonymous: true },
  "/reset-password": {
    url: "/reset-password?token=abc",
    shows: /Set a new password/,
    anonymous: true,
  },
  "/": { url: "/", shows: /Hindi conversations/, data: "GET /api/v1/projects" },
  "/status": {
    url: "/status",
    shows: /1\.0\.0/,
    data: "GET /health/ready",
    normal: ["service not configured"], // a 503 from /health/ready means "not ready", shown as such
  },
  "/account": { url: "/account", shows: /This device/i, data: "GET /api/v1/auth/sessions" },
  "/projects": { url: "/projects", shows: /Hindi conversations/, data: "GET /api/v1/projects" },
  "/projects/:projectId": {
    url: "/projects/p1",
    shows: /HINDI · Hindi conversations/,
    data: "GET /api/v1/projects/p1",
  },
  "/projects/:projectId/team": {
    url: "/projects/p1/team",
    shows: /mona@example\.org/,
    data: "GET /api/v1/projects/p1/members",
  },
  "/projects/:projectId/participants": {
    url: "/projects/p1/participants",
    shows: /P000002/,
    data: "GET /api/v1/projects/p1/participants",
  },
  "/projects/:projectId/audio": { url: "/projects/p1/audio", shows: /^Face-to-face$/ },
  "/projects/:projectId/languages": { url: "/projects/p1/languages", shows: /^Add language$/ },
  "/projects/:projectId/retention": {
    url: "/projects/p1/retention",
    shows: /Days to keep each kind of file/,
  },
  "/projects/:projectId/guidelines": {
    url: "/projects/p1/guidelines",
    shows: /Speak clearly/,
    data: "GET /api/v1/projects/p1/guidelines",
  },
  "/tasks": { url: "/tasks", shows: /T000001/, data: "GET /api/v1/tasks" },
  "/tasks/:taskId": { url: "/tasks/t1", shows: /Task T000001/, data: "GET /api/v1/tasks/t1" },
  "/tasks/:taskId/record": {
    url: "/tasks/t1/record",
    shows: /Record task T000001/,
    data: "GET /api/v1/tasks/t1",
  },
  "/tasks/new": {
    url: "/tasks/new",
    shows: /HINDI Hindi conversations/,
    data: "GET /api/v1/projects",
  },
  "/admin/audit": {
    url: "/admin/audit",
    shows: /project\.created/,
    data: "GET /api/v1/audit-logs",
  },
  "/projects/new": { url: "/projects/new", shows: /New project/ },
  "/admin/users": { url: "/admin/users", shows: /mona@example\.org/, data: "GET /api/v1/users" },
  "/admin/users/new": { url: "/admin/users/new", shows: /Add user/ },
  "/admin/users/import": { url: "/admin/users/import", shows: /Import users/ },
  "/admin/users/:userId": {
    url: "/admin/users/u2",
    shows: /Disable account/,
    data: "GET /api/v1/users/u2",
  },
  "/admin/settings": {
    url: "/admin/settings",
    shows: /staff accounts/i,
    data: "GET /api/v1/settings",
  },
  "*": { url: "/no/such/page", shows: /Page not found/ },
};

export interface FlatRoute {
  path: string;
  auth: boolean;
  permission: string | null;
}

/** Full paths of the route table with the guards that wrap them, read from routes.tsx itself. */
export function flatten(
  items: RouteObject[],
  parent = "",
  auth = false,
  permission: string | null = null,
) {
  const out: FlatRoute[] = [];
  for (const r of items) {
    const element = r.element as ReactElement<{ permission?: string }> | undefined;
    const isAuth = auth || (isValidElement(element) && element.type === RequireAuth);
    const perm =
      isValidElement(element) && element.type === RequirePermission
        ? (element.props.permission ?? null)
        : permission;
    const path = r.index
      ? parent || "/"
      : r.path === undefined
        ? parent
        : r.path === "*" || r.path.startsWith("/")
          ? r.path
          : `${parent === "/" ? "" : parent}/${r.path}`;
    if (r.children) out.push(...flatten(r.children, path, isAuth, perm));
    else out.push({ path, auth: isAuth, permission: perm });
  }
  return out;
}

export const FLAT = flatten(routes);
export const BY_PATH = new Map(FLAT.map((r) => [r.path, r]));

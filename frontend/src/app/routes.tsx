// Route table (FND-015). Pages need sign-in; admin pages also need a permission (usability only).
import { lazy, Suspense, type ComponentType, type ReactElement } from "react";
import { Navigate, type RouteObject } from "react-router";

import { useAuth } from "../auth/AuthContext";
import { RequireAuth, RequirePermission } from "../auth/guards";
import { LoadingState } from "../components/StateViews";
import { LoginPage } from "../auth/LoginPage";
import { ProjectsPage } from "../features/projects/ProjectsPage";
import { AppShell } from "../layouts/AppShell";
import { NotFoundPage } from "../routes/NotFoundPage";
import { loadFresh } from "./staleBuild";

/** A page loaded on first visit, so the first screen does not wait for every page (O11). */
function page<K extends string>(
  load: () => Promise<Record<K, ComponentType>>,
  name: K,
): ReactElement {
  const Page = lazy(() => loadFresh(load).then((m) => ({ default: m[name] as ComponentType })));
  return (
    <Suspense fallback={<LoadingState label="Loading page" />}>
      <Page />
    </Suspense>
  );
}

const tabs = () => import("../features/projects/tabs");

/** The start page: the dashboard for everyone who has one, otherwise the project list. */
function Home(): ReactElement {
  const { can } = useAuth();
  return <Navigate to={can("dashboard.view") ? "/dashboard" : "/projects"} replace />;
}

export const routes: RouteObject[] = [
  // A participant's personal page: opened from a private link, outside the staff application.
  {
    path: "/portal",
    element: page(() => import("../features/portal/PortalPage"), "PortalPage"),
  },
  {
    path: "/",
    element: <AppShell />,
    children: [
      { path: "login", element: <LoginPage /> },
      {
        path: "forgot-password",
        element: page(() => import("../auth/ForgotPasswordPage"), "ForgotPasswordPage"),
      },
      {
        path: "reset-password",
        element: page(() => import("../auth/ResetPasswordPage"), "ResetPasswordPage"),
      },
      {
        element: <RequireAuth />,
        children: [
          { index: true, element: <Home /> },
          {
            path: "two-step-setup",
            element: page(() => import("../auth/TwoStepSetupPage"), "TwoStepSetupPage"),
          },
          {
            element: <RequirePermission permission="dashboard.view" />,
            children: [
              {
                path: "dashboard",
                element: page(() => import("../features/dashboard/DashboardPage"), "DashboardPage"),
              },
            ],
          },
          {
            // The Super Admin only (owner 2026-11-11).
            element: <RequirePermission permission="settings.manage" />,
            children: [
              {
                path: "status",
                element: page(() => import("../features/status/StatusPage"), "StatusPage"),
              },
            ],
          },
          {
            path: "account",
            element: page(() => import("../features/account/AccountPage"), "AccountPage"),
          },
          {
            element: <RequirePermission permission="projects.view" />,
            children: [
              { path: "projects", element: <ProjectsPage /> },
              {
                path: "projects/:projectId",
                element: page(
                  () => import("../features/projects/ProjectDetailPage"),
                  "ProjectDetailPage",
                ),
                children: [
                  { index: true, element: page(tabs, "OverviewTab") },
                  { path: "team", element: page(tabs, "TeamTab") },
                  {
                    path: "participants",
                    element: page(
                      () => import("../features/projects/ParticipantsTab"),
                      "ParticipantsTab",
                    ),
                  },
                  { path: "audio", element: page(tabs, "AudioRulesTab") },
                  { path: "languages", element: page(tabs, "LanguagesTab") },
                  { path: "retention", element: page(tabs, "RetentionTab") },
                  {
                    path: "export",
                    element: page(() => import("../features/projects/ExportTab"), "ExportTab"),
                  },
                ],
              },
              {
                // A participant's own page as they see it; the API answers Super Admins only.
                path: "projects/:projectId/participants/:participantId/page",
                element: page(
                  () => import("../features/portal/ParticipantPagePreview"),
                  "ParticipantPagePreview",
                ),
              },
            ],
          },
          {
            element: <RequirePermission permission="participants.manage" />,
            children: [
              {
                path: "participants",
                element: page(
                  () => import("../features/participants/ParticipantsPage"),
                  "ParticipantsPage",
                ),
              },
            ],
          },
          {
            element: <RequirePermission permission="tasks.view" />,
            children: [
              {
                path: "tasks",
                element: page(() => import("../features/tasks/TasksPage"), "TasksPage"),
              },
              {
                path: "tasks/:taskId",
                element: page(() => import("../features/tasks/TaskDetailPage"), "TaskDetailPage"),
              },
              {
                path: "tasks/:taskId/record",
                element: page(() => import("../features/recording/RecorderPage"), "RecorderPage"),
              },
            ],
          },
          {
            element: <RequirePermission permission="calls.end" />,
            children: [
              {
                path: "calls",
                element: page(() => import("../features/calls/CallsPage"), "CallsPage"),
              },
            ],
          },
          {
            element: <RequirePermission permission="tasks.assign" />,
            children: [
              {
                path: "tasks/new",
                element: page(() => import("../features/tasks/TaskCreatePage"), "TaskCreatePage"),
              },
            ],
          },
          {
            element: <RequirePermission permission="audit.view" />,
            children: [
              {
                path: "admin/audit",
                element: page(() => import("../features/audit/AuditPage"), "AuditPage"),
              },
            ],
          },
          {
            element: <RequirePermission permission="projects.create" />,
            children: [
              {
                path: "projects/new",
                element: page(
                  () => import("../features/projects/ProjectCreatePage"),
                  "ProjectCreatePage",
                ),
              },
            ],
          },
          {
            element: <RequirePermission permission="users.manage" />,
            children: [
              {
                path: "admin/users",
                element: page(() => import("../features/users/UsersPage"), "UsersPage"),
              },
              {
                path: "admin/users/new",
                element: page(() => import("../features/users/UserCreatePage"), "UserCreatePage"),
              },
              {
                path: "admin/users/import",
                element: page(() => import("../features/users/UserImportPage"), "UserImportPage"),
              },
              {
                path: "admin/users/:userId",
                element: page(() => import("../features/users/UserDetailPage"), "UserDetailPage"),
              },
            ],
          },
          {
            element: <RequirePermission permission="settings.manage" />,
            children: [
              {
                path: "admin/settings",
                element: page(() => import("../features/settings/SettingsPage"), "SettingsPage"),
              },
            ],
          },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

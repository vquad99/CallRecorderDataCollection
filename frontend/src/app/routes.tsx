// Route table (FND-015). Pages need sign-in; admin pages also need a permission (usability only).
// Every page route names its page for the browser tab (`handle.title`, see routeTitle.ts); a page
// that fails to display shows RouteError, inside the shell where there is one.
import { lazy, Suspense, type ComponentType, type ReactElement, type ReactNode } from "react";
import { Navigate, type RouteObject } from "react-router";

import { useAuth } from "../auth/AuthContext";
import { RequireAuth, RequirePermission } from "../auth/guards";
import { LoadingState } from "../components/StateViews";
import { LoginPage } from "../auth/LoginPage";
import { ProjectsPage } from "../features/projects/ProjectsPage";
import { AppShell } from "../layouts/AppShell";
import { NotFoundPage } from "../routes/NotFoundPage";
import { RouteError } from "./RouteError";
import { useRouteTitle, type RouteHandle } from "./routeTitle";
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

/** A page outside the shell still gets its tab title. */
function Titled({ children }: { children: ReactNode }) {
  useRouteTitle();
  return children;
}

const tabs = () => import("../features/projects/tabs");
const titled = (title: string): { handle: RouteHandle } => ({ handle: { title } });
const failed = <RouteError />;

/** The start page: the dashboard for everyone who has one, otherwise the project list. */
function Home(): ReactElement {
  const { can } = useAuth();
  return <Navigate to={can("dashboard.view") ? "/dashboard" : "/projects"} replace />;
}

export const routes: RouteObject[] = [
  // A participant's personal page: opened from a private link, outside the staff application.
  {
    path: "/portal",
    ...titled("Your participation"),
    element: <Titled>{page(() => import("../features/portal/PortalPage"), "PortalPage")}</Titled>,
    errorElement: <RouteError standalone />,
  },
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteError standalone />,
    children: [
      { path: "login", ...titled("Sign in"), element: <LoginPage />, errorElement: failed },
      {
        path: "forgot-password",
        ...titled("Reset your password"),
        element: page(() => import("../auth/ForgotPasswordPage"), "ForgotPasswordPage"),
        errorElement: failed,
      },
      {
        path: "reset-password",
        ...titled("Set a new password"),
        element: page(() => import("../auth/ResetPasswordPage"), "ResetPasswordPage"),
        errorElement: failed,
      },
      {
        // A page that fails shows its error here: the top bar and the menu stay.
        element: <RequireAuth />,
        errorElement: failed,
        children: [
          { index: true, element: <Home /> },
          {
            path: "two-step-setup",
            ...titled("Set up two-step sign-in"),
            element: page(() => import("../auth/TwoStepSetupPage"), "TwoStepSetupPage"),
          },
          {
            element: <RequirePermission permission="dashboard.view" />,
            children: [
              {
                path: "dashboard",
                ...titled("Dashboard"),
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
                ...titled("System status"),
                element: page(() => import("../features/status/StatusPage"), "StatusPage"),
              },
            ],
          },
          {
            path: "account",
            ...titled("My account"),
            element: page(() => import("../features/account/AccountPage"), "AccountPage"),
          },
          {
            element: <RequirePermission permission="projects.view" />,
            children: [
              { path: "projects", ...titled("Projects"), element: <ProjectsPage /> },
              {
                // The page adds the project's code once it has loaded (ProjectDetailPage).
                path: "projects/:projectId",
                ...titled("Project"),
                element: page(
                  () => import("../features/projects/ProjectDetailPage"),
                  "ProjectDetailPage",
                ),
                children: [
                  { index: true, element: page(tabs, "OverviewTab") },
                  {
                    // Collected against the project's targets (D-148).
                    path: "progress",
                    ...titled("Progress"),
                    element: page(() => import("../features/projects/ProgressTab"), "ProgressTab"),
                  },
                  { path: "team", ...titled("Team"), element: page(tabs, "TeamTab") },
                  {
                    path: "participants",
                    ...titled("Participants"),
                    element: page(
                      () => import("../features/projects/ParticipantsTab"),
                      "ParticipantsTab",
                    ),
                  },
                  {
                    path: "tasks",
                    ...titled("Tasks"),
                    element: page(
                      () => import("../features/projects/ProjectTasksTab"),
                      "ProjectTasksTab",
                    ),
                  },
                  {
                    path: "audio",
                    ...titled("Audio rules"),
                    element: page(tabs, "AudioRulesTab"),
                  },
                  {
                    // The project's rules (D-145): one section at a time (D-150); the Rules
                    // page's own address opens the first.
                    path: "rules",
                    ...titled("Rules"),
                    children: [
                      { index: true, element: <Navigate to="speakers" replace /> },
                      {
                        path: ":section",
                        element: page(() => import("../features/projects/RulesTab"), "RulesTab"),
                      },
                    ],
                  },
                  {
                    path: "languages",
                    ...titled("Languages"),
                    element: page(tabs, "LanguagesTab"),
                  },
                  {
                    path: "retention",
                    ...titled("Retention"),
                    element: page(tabs, "RetentionTab"),
                  },
                  {
                    path: "export",
                    ...titled("Export"),
                    element: page(() => import("../features/projects/ExportTab"), "ExportTab"),
                  },
                ],
              },
              {
                // A participant's own page as they see it; the API answers Super Admins only.
                path: "projects/:projectId/participants/:participantId/page",
                ...titled("Participant page"),
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
                ...titled("Participants"),
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
                ...titled("Tasks"),
                element: page(() => import("../features/tasks/TasksPage"), "TasksPage"),
              },
              {
                path: "tasks/:taskId",
                ...titled("Task"),
                element: page(() => import("../features/tasks/TaskDetailPage"), "TaskDetailPage"),
              },
              {
                path: "tasks/:taskId/record",
                ...titled("Recorder"),
                element: page(() => import("../features/recording/RecorderPage"), "RecorderPage"),
              },
            ],
          },
          {
            element: <RequirePermission permission="calls.end" />,
            children: [
              {
                path: "calls",
                ...titled("Phone calls"),
                element: page(() => import("../features/calls/CallsPage"), "CallsPage"),
              },
            ],
          },
          {
            element: <RequirePermission permission="tasks.assign" />,
            children: [
              {
                path: "tasks/new",
                ...titled("New task"),
                element: page(() => import("../features/tasks/TaskCreatePage"), "TaskCreatePage"),
              },
            ],
          },
          {
            // The Super Admin and Project Admins (D-137).
            element: <RequirePermission permission="payments.manage" />,
            children: [
              {
                path: "payments",
                ...titled("Payments"),
                element: page(() => import("../features/payments/PaymentsPage"), "PaymentsPage"),
              },
            ],
          },
          {
            element: <RequirePermission permission="audit.view" />,
            children: [
              {
                path: "admin/audit",
                ...titled("Audit log"),
                element: page(() => import("../features/audit/AuditPage"), "AuditPage"),
              },
            ],
          },
          {
            element: <RequirePermission permission="projects.create" />,
            children: [
              {
                path: "projects/new",
                ...titled("New project"),
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
                ...titled("Users"),
                element: page(() => import("../features/users/UsersPage"), "UsersPage"),
              },
              {
                path: "admin/users/new",
                ...titled("Add user"),
                element: page(() => import("../features/users/UserCreatePage"), "UserCreatePage"),
              },
              {
                path: "admin/users/import",
                ...titled("Import users"),
                element: page(() => import("../features/users/UserImportPage"), "UserImportPage"),
              },
              {
                path: "admin/users/:userId",
                ...titled("User"),
                element: page(() => import("../features/users/UserDetailPage"), "UserDetailPage"),
              },
            ],
          },
          {
            element: <RequirePermission permission="settings.manage" />,
            children: [
              {
                path: "admin/settings",
                ...titled("Settings"),
                element: page(() => import("../features/settings/SettingsPage"), "SettingsPage"),
              },
            ],
          },
          { path: "*", ...titled("Page not found"), element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

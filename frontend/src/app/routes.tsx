// Route table (FND-015). Pages need sign-in; admin pages also need a permission (usability only).
import type { RouteObject } from "react-router";

import { ForgotPasswordPage } from "../auth/ForgotPasswordPage";
import { RequireAuth, RequirePermission } from "../auth/guards";
import { LoginPage } from "../auth/LoginPage";
import { ResetPasswordPage } from "../auth/ResetPasswordPage";
import { AccountPage } from "../features/account/AccountPage";
import { ProjectCreatePage } from "../features/projects/ProjectCreatePage";
import { ProjectDetailPage } from "../features/projects/ProjectDetailPage";
import { ProjectsPage } from "../features/projects/ProjectsPage";
import {
  AudioRulesTab,
  GuidelinesTab,
  LanguagesTab,
  OverviewTab,
  RetentionTab,
  TeamTab,
} from "../features/projects/tabs";
import { SettingsPage } from "../features/settings/SettingsPage";
import { StatusPage } from "../features/status/StatusPage";
import { UserCreatePage } from "../features/users/UserCreatePage";
import { UserDetailPage } from "../features/users/UserDetailPage";
import { UserImportPage } from "../features/users/UserImportPage";
import { UsersPage } from "../features/users/UsersPage";
import { AppShell } from "../layouts/AppShell";
import { NotFoundPage } from "../routes/NotFoundPage";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [
      { path: "login", element: <LoginPage /> },
      { path: "forgot-password", element: <ForgotPasswordPage /> },
      { path: "reset-password", element: <ResetPasswordPage /> },
      {
        element: <RequireAuth />,
        children: [
          { index: true, element: <ProjectsPage /> },
          { path: "status", element: <StatusPage /> },
          { path: "account", element: <AccountPage /> },
          {
            element: <RequirePermission permission="projects.view" />,
            children: [
              { path: "projects", element: <ProjectsPage /> },
              {
                path: "projects/:projectId",
                element: <ProjectDetailPage />,
                children: [
                  { index: true, element: <OverviewTab /> },
                  { path: "team", element: <TeamTab /> },
                  { path: "audio", element: <AudioRulesTab /> },
                  { path: "languages", element: <LanguagesTab /> },
                  { path: "retention", element: <RetentionTab /> },
                  { path: "guidelines", element: <GuidelinesTab /> },
                ],
              },
            ],
          },
          {
            element: <RequirePermission permission="projects.create" />,
            children: [{ path: "projects/new", element: <ProjectCreatePage /> }],
          },
          {
            element: <RequirePermission permission="users.manage" />,
            children: [
              { path: "admin/users", element: <UsersPage /> },
              { path: "admin/users/new", element: <UserCreatePage /> },
              { path: "admin/users/import", element: <UserImportPage /> },
              { path: "admin/users/:userId", element: <UserDetailPage /> },
            ],
          },
          {
            element: <RequirePermission permission="settings.manage" />,
            children: [{ path: "admin/settings", element: <SettingsPage /> }],
          },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

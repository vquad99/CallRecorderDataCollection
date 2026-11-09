// Route table (FND-015).
import type { RouteObject } from "react-router";

import { StatusPage } from "../features/status/StatusPage";
import { AppShell } from "../layouts/AppShell";
import { NotFoundPage } from "../routes/NotFoundPage";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <StatusPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";

import { routes } from "./app/routes";
import { ErrorBoundary } from "./components/ErrorBoundary";
import "./styles/global.css";

const root = document.getElementById("root");
if (!root) throw new Error("Root element #root is missing from index.html");

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <RouterProvider router={createBrowserRouter(routes)} />
    </ErrorBoundary>
  </StrictMode>,
);

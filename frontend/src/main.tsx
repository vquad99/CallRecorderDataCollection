import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";

import { routes } from "./app/routes";
import { AuthProvider } from "./auth/AuthContext";
import { ErrorBoundary } from "./components/ErrorBoundary";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "./styles/global.css";

const root = document.getElementById("root");
if (!root) throw new Error("Root element #root is missing from index.html");

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <AuthProvider>
        <RouterProvider router={createBrowserRouter(routes)} />
      </AuthProvider>
    </ErrorBoundary>
  </StrictMode>,
);

// What a page that failed to display shows instead (FEA-01): the app's own message, never the
// error's text or its stack. Under the shell the top bar and the menu stay, and choosing another
// page clears it. Imported directly, not loaded on demand: a page file that failed to download is
// one of the causes (the stale-build reload in staleBuild.ts has already been tried by then).
import { useEffect } from "react";
import { Link, useLocation, useRouteError } from "react-router";

import { ErrorState } from "../components/StateViews";
import { usePageTitle } from "../hooks/usePageTitle";

/** `standalone`: nothing of the app around it (the participant page, or the shell itself failed). */
export function RouteError({ standalone = false }: { standalone?: boolean }) {
  const error = useRouteError();
  const { pathname } = useLocation();
  useEffect(() => {
    console.error("A page failed to display", error);
  }, [error]);
  usePageTitle("Page could not be shown");
  // The participant page leads nowhere into the staff application.
  const participant = pathname.startsWith("/portal");
  const state = (
    <ErrorState
      title="This page could not be shown"
      message="Reload the page to try again. If it keeps happening, tell your administrator."
      onRetry={() => window.location.reload()}
      action={participant ? undefined : <Link to="/">Go to the start page</Link>}
    />
  );
  return standalone ? (
    <main id="main" className="route-error">
      {state}
    </main>
  ) : (
    state
  );
}

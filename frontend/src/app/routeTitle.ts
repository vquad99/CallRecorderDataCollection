// Each page's tab title (WCAG 2.4.2): the route's own `handle.title` (routes.tsx), the deepest one
// that has one. Set in a layout effect when the address changes, before any page's passive effects
// run, so a page that knows more (usePageTitle: a task's code, a project's name) still wins, and a
// re-render on the same address leaves the page's title alone.
import { useLayoutEffect } from "react";
import { useLocation, useMatches } from "react-router";

import { pageTitle } from "../hooks/usePageTitle";

export interface RouteHandle {
  /** The page's name in the browser tab, before the product's. */
  title?: string;
}

export function useRouteTitle(): void {
  const { pathname } = useLocation();
  const title = useMatches()
    .map((m) => (m.handle as RouteHandle | undefined)?.title)
    .filter(Boolean)
    .pop();
  useLayoutEffect(() => {
    document.title = pageTitle(title);
  }, [pathname, title]);
}

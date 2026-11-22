// The browser tab's title (WCAG 2.4.2): the page's own words, then the product. The shell sets each
// route's plain title first (routes.tsx `handle.title`, in a layout effect); a page that knows more,
// such as a task's code or a project's name, refines it here once its data has loaded.
import { useEffect } from "react";

export const PRODUCT = "Conversation Collection";

/** "Task T000127 · Conversation Collection": the non-empty parts, then the product. */
export function pageTitle(...parts: (string | null | undefined)[]): string {
  return [...parts.filter((p): p is string => Boolean(p?.trim())), PRODUCT].join(" · ");
}

/** Sets the tab's title to `pageTitle(...parts)`; does nothing while every part is empty (still
 * loading), so the route's plain title stays until there is something better. */
export function usePageTitle(...parts: (string | null | undefined)[]): void {
  const title = parts.some((p) => Boolean(p?.trim())) ? pageTitle(...parts) : null;
  useEffect(() => {
    if (title !== null) document.title = title;
  }, [title]);
}

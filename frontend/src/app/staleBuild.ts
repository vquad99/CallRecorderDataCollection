// After an update, a page opened before it asks for files of the old version, which no longer
// exist ("Failed to fetch dynamically imported module"). Load the new version once instead of
// showing an error (D-089).

const KEY = "ccp-reloaded-for-update";
const QUIET_MS = 30_000; // never reload twice within this time: a real outage must still show

const STALE = [
  /dynamically imported module/i, // Chrome, Edge
  /Importing a module script failed/i, // Safari
  /error loading dynamically imported module/i, // Firefox
  /Unable to preload CSS/i, // a page's stylesheet
];

export function isStaleBuildError(error: unknown): boolean {
  const text = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
  return STALE.some((pattern) => pattern.test(text));
}

/** Reloads the page unless it already did so moments ago. True when a reload was started. */
export function reloadOnce(
  reload: () => void = () => window.location.reload(),
  now: number = Date.now(),
): boolean {
  let last = 0;
  try {
    last = Number(window.sessionStorage.getItem(KEY) ?? 0);
  } catch {
    // Storage blocked (private mode, policy): still reload once; this page then shows the error.
  }
  if (now - last < QUIET_MS) return false;
  try {
    window.sessionStorage.setItem(KEY, String(now));
  } catch {
    // see above
  }
  reload();
  return true;
}

/** Wraps a page's loader: an old-version file error reloads the page instead of failing. */
export function loadFresh<T>(load: () => Promise<T>, reload?: () => void): Promise<T> {
  return load().catch((error: unknown) => {
    if (isStaleBuildError(error) && reloadOnce(reload)) {
      return new Promise<T>(() => {}); // the page is reloading; keep showing "Loading page"
    }
    throw error;
  });
}

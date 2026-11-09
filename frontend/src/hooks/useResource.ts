// Load data for a page with loading / loaded / failed states and a reload function.
// State only changes when a request settles; "loading" is derived from a newer request token.
import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError } from "../api/client";

export type Resource<T> =
  { status: "loading" } | { status: "loaded"; data: T } | { status: "failed"; error: ApiError };

export function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError({ status: 0, code: "UNKNOWN", message: "Unexpected error" });
}

const LOADING = { status: "loading" } as const;

export function useResource<T>(load: () => Promise<T>, deps: readonly unknown[]) {
  const [version, setVersion] = useState(0);
  // A fresh object whenever the inputs change; results for an older token are ignored.
  const key = JSON.stringify(deps);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const token = useMemo(() => ({}), [key, version]);
  const [result, setResult] = useState<{ token: object; value: Resource<T> } | null>(null);

  useEffect(() => {
    let active = true;
    load()
      .then((data) => active && setResult({ token, value: { status: "loaded", data } }))
      .catch(
        (error: unknown) =>
          active && setResult({ token, value: { status: "failed", error: toApiError(error) } }),
      );
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const state: Resource<T> = result && result.token === token ? result.value : LOADING;
  const reload = useCallback(() => setVersion((n) => n + 1), []);
  const replace = useCallback(
    (data: T) => setResult({ token, value: { status: "loaded", data } }),
    [token],
  );
  return { state, reload, replace };
}

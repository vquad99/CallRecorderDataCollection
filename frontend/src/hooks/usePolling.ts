// Data that changes on the server by itself (a phone call, an export being prepared): loaded like
// any page data, then fetched again quietly every few seconds while `keepGoing` says it is still
// changing. What is on screen stays until the newer answer replaces it, and an older answer that
// arrives late never replaces a newer one.
import { useCallback, useEffect, useRef } from "react";

import { useResource } from "./useResource";

export function usePolling<T>(
  load: () => Promise<T>,
  deps: readonly unknown[],
  everyMs: number,
  keepGoing: (data: T) => boolean,
) {
  const { state, reload, replace } = useResource(load, deps);
  const latestLoad = useRef(load);
  useEffect(() => {
    latestLoad.current = load;
  });
  const newest = useRef(0);
  const refresh = useCallback(() => {
    const mine = ++newest.current;
    return latestLoad
      .current()
      .then((data) => {
        if (mine === newest.current) replace(data);
      })
      .catch(() => undefined);
  }, [replace]);
  const moving = state.status === "loaded" && keepGoing(state.data);
  useEffect(() => {
    if (!moving) return;
    const timer = window.setInterval(() => void refresh(), everyMs);
    return () => window.clearInterval(timer);
  }, [moving, refresh, everyMs]);
  return { state, reload, replace, refresh };
}

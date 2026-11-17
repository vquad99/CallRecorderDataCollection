// One way to run an action from a button or form: what is busy, what went wrong, what was done.
import { useState } from "react";

import type { ApiError } from "../api/client";
import { toApiError } from "./useResource";

/**
 * `run(action, key)` marks `key` busy, clears the last message and error, and runs the action. A
 * string the action returns becomes the message; a failure becomes the error. Resolves true when
 * the action worked. `onDone` runs after every success (for example to load a list again);
 * `initialMessage` is shown until the first action (a message handed over by the page before).
 */
export function useAction(onDone?: () => void, initialMessage: string | null = null) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(initialMessage);

  async function run(action: () => Promise<unknown>, key = "action"): Promise<boolean> {
    setBusy(key);
    setError(null);
    setMessage(null);
    try {
      const result = await action();
      if (typeof result === "string") setMessage(result);
      onDone?.();
      return true;
    } catch (err) {
      setError(toApiError(err));
      return false;
    } finally {
      setBusy(null);
    }
  }

  return { busy, error, message, run, setMessage };
}

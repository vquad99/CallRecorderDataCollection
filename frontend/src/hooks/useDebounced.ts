// A value that follows another once it has stopped changing for a moment, so a search box asks the
// server when typing pauses, not on every key (O7).
import { useEffect, useState } from "react";

const TYPING_PAUSE_MS = 300;

export function useDebounced<T>(value: T, ms = TYPING_PAUSE_MS): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setSettled(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return settled;
}

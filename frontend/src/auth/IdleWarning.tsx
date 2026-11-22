// The server ends a session after some minutes without a request (D-122). Two minutes before the
// page's own count runs out this strip says so and offers to stay signed in; when the time is up
// it asks the server, which then shows the sign-in page. Only requests count as activity: this
// strip's own clock and its check at the end do not (the check is a background request), so a tab
// left open still lets the session end.
import { useEffect, useRef, useState } from "react";

import { getMe } from "../api/auth";
import { ApiError, inBackground, lastApiActivity } from "../api/client";
import { Button } from "../components/form/Button";
import { Icon } from "../components/Icon";
import { ErrorNotice } from "../components/Notice";
import { useAction } from "../hooks/useAction";
import { useAuth } from "./AuthContext";

const WARN_MS = 60_000;
// The server records use at most once a minute (backend deps.py _LAST_SEEN_WRITE_INTERVAL), so
// its count can end up to a minute before the page's: warn that much earlier.
const SERVER_LAG_MS = 60_000;
const CHECK_EVERY_MS = 5_000;
// Past the page's count, another tab may still be keeping the session: ask at most this often.
const ASK_EVERY_MS = 60_000;

const signedOut = (error: unknown) => error instanceof ApiError && error.status === 401;

export function IdleWarning({ idleMinutes }: { idleMinutes: number }) {
  const { refresh } = useAuth();
  const [warning, setWarning] = useState(false);
  const { busy, error, run } = useAction();
  const asked = useRef(0);
  useEffect(() => {
    const idle = idleMinutes * 60_000;
    const check = () => {
      const left = idle - (Date.now() - lastApiActivity());
      setWarning(left > 0 && left <= WARN_MS + SERVER_LAG_MS);
      if (left > 0 || Date.now() - asked.current < ASK_EVERY_MS) return;
      // Time is up: the server decides. A session that ended leads to the sign-in page.
      asked.current = Date.now();
      inBackground(getMe).catch((e: unknown) => {
        if (signedOut(e)) void refresh();
      });
    };
    const timer = window.setInterval(check, CHECK_EVERY_MS);
    return () => window.clearInterval(timer);
  }, [idleMinutes, refresh]);
  if (!warning) return null;
  return (
    <div className="idle-warning" role="alert">
      <Icon name="clock" size={16} />
      <span>You will be signed out in under 2 minutes.</span>
      <Button
        variant="secondary"
        busy={busy !== null}
        onClick={() =>
          void run(async () => {
            try {
              await getMe();
              setWarning(false);
            } catch (e) {
              // Already ended: the sign-in page, saying the session expired.
              if (signedOut(e)) await refresh();
              else throw e;
            }
          })
        }
      >
        Stay signed in
      </Button>
      <ErrorNotice error={error} />
    </div>
  );
}

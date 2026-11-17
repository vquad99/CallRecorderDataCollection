// The server ends a session after some minutes without a request (D-122). One minute before that
// this strip says so and offers to stay signed in; when the time is up it asks the server, which
// then shows the sign-in page. Only requests count as activity: this strip's own clock does not.
import { useEffect, useState } from "react";

import { getMe } from "../api/auth";
import { lastApiActivity } from "../api/client";
import { Button } from "../components/form/Button";
import { Icon } from "../components/Icon";
import { ErrorNotice } from "../components/Notice";
import { useAction } from "../hooks/useAction";
import { useAuth } from "./AuthContext";

const WARN_MS = 60_000;
const CHECK_EVERY_MS = 5_000;

export function IdleWarning({ idleMinutes }: { idleMinutes: number }) {
  const { refresh } = useAuth();
  const [warning, setWarning] = useState(false);
  const { busy, error, run } = useAction();
  useEffect(() => {
    const idle = idleMinutes * 60_000;
    const check = () => {
      const left = idle - (Date.now() - lastApiActivity());
      // Time is up: the server decides; a session that ended leads to the sign-in page.
      if (left <= 0) void refresh();
      setWarning(left > 0 && left <= WARN_MS);
    };
    const timer = window.setInterval(check, CHECK_EVERY_MS);
    return () => window.clearInterval(timer);
  }, [idleMinutes, refresh]);
  if (!warning) return null;
  return (
    <div className="idle-warning" role="alert">
      <Icon name="clock" size={16} />
      <span>You will be signed out in 1 minute.</span>
      <Button
        variant="secondary"
        busy={busy !== null}
        onClick={() =>
          void run(async () => {
            await getMe();
            setWarning(false);
          })
        }
      >
        Stay signed in
      </Button>
      <ErrorNotice error={error} />
    </div>
  );
}

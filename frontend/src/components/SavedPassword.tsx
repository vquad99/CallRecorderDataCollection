// A saved password, hidden until the person clicks Show (D-130). Each Show asks the server again,
// which keeps a record of who looked; Hide covers it again.
import { useState } from "react";

import { useAction } from "../hooks/useAction";
import { Button } from "./form/Button";
import { ErrorNotice } from "./Notice";

export function SavedPassword({
  label,
  load,
}: {
  label: string;
  load: () => Promise<{ password: string }>;
}) {
  const [shown, setShown] = useState<string | null>(null);
  const { busy, error, run } = useAction();
  return (
    <div className="stack">
      <p className="actions">
        <span>
          {label}:{" "}
          {shown === null ? (
            <>
              <span aria-hidden="true">••••••••</span>
              <span className="sr-only">hidden</span>
            </>
          ) : (
            <code>{shown}</code>
          )}
        </span>
        <Button
          variant="secondary"
          icon="eye"
          busy={busy !== null}
          onClick={() =>
            shown === null
              ? void run(async () => setShown((await load()).password))
              : setShown(null)
          }
        >
          {shown === null ? "Show" : "Hide"}
        </Button>
      </p>
      <ErrorNotice error={error} />
    </div>
  );
}

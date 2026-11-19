// Listening to a recording on the task page: a Listen button that fetches a short-lived link, and
// the newest finished recording of a task (D-092).
import { useState } from "react";

import * as rec from "../../api/recordings";
import { Button } from "../../components/form/Button";
import { ErrorNotice } from "../../components/Notice";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";

export function Player({ assetId, label = "Recording" }: { assetId: string; label?: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const { busy, error, run } = useAction();
  if (src) {
    // Speech recordings carry no captions.
    // eslint-disable-next-line jsx-a11y/media-has-caption
    return <audio controls src={src} className="player" aria-label={label} />;
  }
  return (
    <div>
      <Button
        variant="secondary"
        icon="play"
        busy={busy !== null}
        onClick={() => void run(async () => setSrc((await rec.assetUrl(assetId, "play")).url))}
      >
        Listen
      </Button>
      <ErrorNotice error={error} />
    </div>
  );
}

/** The delivery file of the task's current recording (its newest finished one), to listen to. */
export function ListenLatest({ taskId }: { taskId: string }) {
  const { state } = useResource(() => rec.listRecordings(taskId), [taskId]);
  if (state.status !== "loaded") return null;
  const latest = state.data.find((r) => r.current);
  const asset = latest ? rec.deliveryAsset(latest.assets) : undefined;
  return asset ? (
    <Player assetId={asset.id} />
  ) : (
    <p className="muted">No finished recording yet.</p>
  );
}

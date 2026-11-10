// System status page: shows what the backend reports about itself (health + version).
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import { getReadiness, getVersion, type Readiness, type VersionInfo } from "../../api/system";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { IconTile } from "../../components/Icon";

type LoadState =
  | { kind: "loading" }
  | { kind: "loaded"; readiness: Readiness; version: VersionInfo }
  | { kind: "failed"; error: ApiError };

const CHECK_LABELS: Record<string, string> = {
  ok: "OK",
  error: "Not reachable",
  not_configured: "Not configured",
};

export function StatusPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getReadiness(controller.signal), getVersion(controller.signal)])
      .then(([readiness, version]) => setState({ kind: "loaded", readiness, version }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const apiError =
          error instanceof ApiError
            ? error
            : new ApiError({ status: 0, code: "UNKNOWN", message: "Unexpected error" });
        setState({ kind: "failed", error: apiError });
      });
    return () => controller.abort();
  }, [attempt]);

  const retry = useCallback(() => {
    setState({ kind: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  return (
    <section aria-labelledby="status-title">
      <h1 id="status-title">
        <IconTile name="status" tone="green" />
        System status
      </h1>
      {state.kind === "loading" ? <LoadingState label="Checking the server" /> : null}
      {state.kind === "failed" ? (
        <ErrorState title="Server status unavailable" error={state.error} onRetry={retry} />
      ) : null}
      {state.kind === "loaded" ? (
        <div className="card">
          <p className={`status status--${state.readiness.status}`}>
            {state.readiness.status === "ready" ? "Ready" : "Not ready"}
          </p>
          <dl className="checks">
            {Object.entries(state.readiness.checks).map(([name, value]) => (
              <div key={name} className="checks__row">
                <dt>{name}</dt>
                <dd>{CHECK_LABELS[value] ?? value}</dd>
              </div>
            ))}
          </dl>
          <p className="state__meta">
            Version {state.version.version} ({state.version.environment})
          </p>
          <button type="button" className="button button--secondary" onClick={retry}>
            Check again
          </button>
        </div>
      ) : null}
    </section>
  );
}

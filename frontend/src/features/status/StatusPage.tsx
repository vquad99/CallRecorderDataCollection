// System status page: shows what the backend reports about itself (health + version).
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import {
  type OperationAlerts,
  type Readiness,
  type VersionInfo,
  getSystemStatus,
} from "../../api/system";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { when } from "../../lib/format";

type LoadState =
  | { kind: "loading" }
  | { kind: "loaded"; readiness: Readiness; version: VersionInfo; alerts: OperationAlerts | null }
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
    getSystemStatus(controller.signal)
      .then((s) =>
        setState({ kind: "loaded", readiness: s, version: s.version, alerts: s.alerts ?? null }),
      )
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
    <section aria-labelledby="status-title" className="stack">
      <div className="page-header">
        <div className="page-header__text">
          <h1 id="status-title">System status</h1>
          <p className="page-header__lead">Whether the server and its services are working.</p>
        </div>
        {/* The page's button, as on every page: its own row on a phone (D-158). */}
        {state.kind === "loaded" ? (
          <div className="actions">
            <Button variant="secondary" icon="refresh" onClick={retry}>
              Check again
            </Button>
          </div>
        ) : null}
      </div>
      {state.kind === "loading" ? <LoadingState label="Checking the server" /> : null}
      {state.kind === "failed" ? (
        <ErrorState title="Server status unavailable" error={state.error} onRetry={retry} />
      ) : null}
      {state.kind === "loaded" ? (
        <section className="card stack stack--tight" aria-labelledby="server-title">
          <div className="card__head">
            <h2 id="server-title">Server</h2>
            <p className={`status status--${state.readiness.status}`}>
              {state.readiness.status === "ready" ? "Ready" : "Not ready"}
            </p>
          </div>
          <DataTable label="Server checks" className="status-table">
            <thead>
              <tr>
                <th scope="col">Part</th>
                <th scope="col">State</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(state.readiness.checks).map(([name, value]) => (
                <tr key={name}>
                  <th scope="row" className="status-table__name">
                    {name}
                  </th>
                  <td>{CHECK_LABELS[value] ?? value}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
          <p className="state__meta">
            Version {state.version.version} ({state.version.environment})
          </p>
        </section>
      ) : null}
      {state.kind === "loaded" && state.alerts ? (
        <section className="card stack stack--tight" aria-labelledby="attention-title">
          <h2 id="attention-title">Needs attention</h2>
          {state.alerts.active.length === 0 ? (
            <p>Nothing: the platform found nothing wrong at its last look.</p>
          ) : (
            <ul className="list" aria-label="What needs attention">
              {state.alerts.active.map((a) => (
                <li key={a.code}>
                  <strong>{a.summary}</strong>
                  <div className="muted">Since {when(a.since)}</div>
                </li>
              ))}
            </ul>
          )}
          <p className="muted">
            {state.alerts.email_configured
              ? `The platform looks every minute and emails ${state.alerts.recipients} ` +
                `address${state.alerts.recipients === 1 ? "" : "es"} when something new is wrong.`
              : "The platform looks every minute. Nobody is told by email yet: set ALERT_EMAIL " +
                "on the server to get a message when something is wrong."}
          </p>
        </section>
      ) : null}
    </section>
  );
}

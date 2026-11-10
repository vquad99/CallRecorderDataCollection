// A participant's personal page (D-067): opened from a private link, no account. Shows the
// project's consent form with the participant's answer, and their own sessions.
import { useState } from "react";
import { useLocation } from "react-router";

import { ApiError } from "../../api/client";
import { answerConsent, getPortal, type PortalView } from "../../api/portal";
import { Button } from "../../components/form/Button";
import { BrandMark, Icon, IconTile } from "../../components/Icon";
import { ErrorNotice } from "../../components/Notice";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { toApiError, useResource } from "../../hooks/useResource";
import "./portal.css";

const day = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const minutes = (m: number) => (m >= 60 ? `${(m / 60).toFixed(1)} h` : `${Math.round(m)} min`);
const TONE: Record<string, string> = {
  Accepted: "APPROVED",
  "Recorded, being checked": "AUDIO_QC",
  Planned: "ASSIGNED",
  "To be recorded again": "RETURNED",
  "Not used": "CANCELLED",
};
const ANSWER: Record<string, { label: string; tone: string }> = {
  GIVEN: { label: "You agreed", tone: "APPROVED" },
  REFUSED: { label: "You did not agree", tone: "REJECTED" },
  WITHDRAWN: { label: "You withdrew your consent", tone: "RETURNED" },
};

function Consent({
  view,
  token,
  onChange,
}: {
  view: PortalView;
  token: string;
  onChange: (v: PortalView) => void;
}) {
  const [read, setRead] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const sentBack = view.consent_status === "GIVEN" && view.consent_review === "REJECTED";
  const answer = sentBack
    ? { label: "Please answer again", tone: "RETURNED" }
    : view.consent_status === "GIVEN" && view.consent_review === "APPROVED"
      ? { label: "You agreed · confirmed by the team", tone: "APPROVED" }
      : view.consent_status
        ? ANSWER[view.consent_status]
        : undefined;

  function send(decision: "GIVEN" | "REFUSED" | "WITHDRAWN") {
    setBusy(true);
    setError(null);
    answerConsent(token, decision)
      .then(onChange)
      .catch((err: unknown) => setError(toApiError(err)))
      .finally(() => setBusy(false));
  }

  return (
    <section className="card stack" aria-labelledby="consent-title">
      <div className="page-header">
        <h2 id="consent-title" className="with-icon">
          <IconTile name="verified" tone="green" size={28} />
          Consent form
        </h2>
        {answer ? (
          <StatusBadge status={answer.tone} label={answer.label} />
        ) : (
          <StatusBadge status="ON_HOLD" label="Waiting for your answer" />
        )}
      </div>
      {view.consent_text.trim() ? (
        <>
          <div className="consent-text">{view.consent_text}</div>
          <p className="muted">
            Version {view.consent_policy_version}
            {view.consent_at ? ` · your answer was saved on ${day(view.consent_at)}` : ""}
          </p>
          {sentBack ? (
            <p className="notice notice--error" role="status">
              The project team could not accept your answer: {view.consent_review_note} Please read
              the form and answer again.
            </p>
          ) : null}
          {view.consent_status === "GIVEN" && !sentBack ? (
            <div className="actions">
              <Button variant="secondary" busy={busy} onClick={() => send("WITHDRAWN")}>
                Withdraw my consent
              </Button>
            </div>
          ) : (
            <>
              <label className="checkbox">
                <input type="checkbox" checked={read} onChange={(e) => setRead(e.target.checked)} />
                I have read and understood this form
              </label>
              <div className="actions">
                <Button busy={busy} disabled={!read} onClick={() => send("GIVEN")}>
                  <Icon name="check" size={16} weight="bold" />I agree
                </Button>
                {view.consent_status !== "REFUSED" ? (
                  <Button
                    variant="secondary"
                    busy={busy}
                    disabled={!read}
                    onClick={() => send("REFUSED")}
                  >
                    I do not agree
                  </Button>
                ) : null}
              </div>
            </>
          )}
        </>
      ) : (
        <p className="muted">The project team has not published the consent form yet.</p>
      )}
      <ErrorNotice error={error} />
    </section>
  );
}

export function PortalPage() {
  // The secret is the part after "#": browsers never send it to a server or write it to a log.
  const token = useLocation().hash.replace(/^#/, "");
  const { state, reload, replace } = useResource(
    () =>
      token
        ? getPortal(token)
        : Promise.reject(
            new ApiError({
              status: 404,
              code: "LINK_INVALID",
              message: "This link is incomplete. Open the full link you were given.",
            }),
          ),
    [token],
  );
  return (
    <div className="portal">
      <header className="portal__bar">
        <span className="brand">
          <BrandMark />
          <span className="brand__name">Conversation Collection</span>
        </span>
        <span className="portal__tag">
          <Icon name="lock" size={14} /> Private page
        </span>
      </header>
      <main id="main" className="portal__main">
        {state.status === "loading" ? <LoadingState label="Loading your page" /> : null}
        {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
        {state.status === "loaded" ? (
          <div className="stack">
            <div className="portal__hero">
              <IconTile name="user" tone="blue" size={48} />
              <div>
                <h1>Your participation</h1>
                <p className="muted">
                  {state.data.project_name} · participant {state.data.participant_code}
                </p>
              </div>
            </div>
            <div className="portal__stats">
              <div className="card">
                <p className="muted">Sessions</p>
                <p className="portal__num">{state.data.sessions.length}</p>
              </div>
              <div className="card">
                <p className="muted">Accepted recording time</p>
                <p className="portal__num">{minutes(state.data.accepted_minutes)}</p>
              </div>
            </div>
            <Consent view={state.data} token={token} onChange={replace} />
            <section className="stack stack--tight" aria-labelledby="sessions-title">
              <h2 id="sessions-title">Your sessions</h2>
              {state.data.sessions.length === 0 ? (
                <EmptyState
                  title="No sessions yet"
                  message="Your recording sessions will appear here."
                />
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th scope="col">Session</th>
                        <th scope="col">Date</th>
                        <th scope="col">Type</th>
                        <th scope="col">Length</th>
                        <th scope="col">State</th>
                      </tr>
                    </thead>
                    <tbody>
                      {state.data.sessions.map((s) => (
                        <tr key={s.task_code}>
                          <td className="mono">{s.task_code}</td>
                          <td>{day(s.day)}</td>
                          <td>
                            <span className="cell-icon">
                              <Icon name={s.mode === "TELEPHONY" ? "phone" : "mic"} size={15} />
                              {s.mode === "TELEPHONY" ? "Phone call" : "In person"}
                            </span>
                          </td>
                          <td>{s.minutes === null ? "-" : minutes(s.minutes)}</td>
                          <td>
                            <StatusBadge status={TONE[s.state] ?? "DRAFT"} label={s.state} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
            <p className="muted">
              This private link works until {day(state.data.link_expires_at)}. Do not share it. To
              ask a question or have your data removed, contact the project team.
            </p>
          </div>
        ) : null}
      </main>
    </div>
  );
}

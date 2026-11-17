// A participant's personal page (D-067): opened from a private link, no account. Shows the
// participant's own details, minutes and sessions (read-only) and the project's consent form with
// their answer (D-100). The answer counts at once; "I agree" is final, with nothing to withdraw
// (D-129). The same page, without the answer buttons, is the Super Admin's view.
import { useState } from "react";
import { useLocation } from "react-router";

import { ApiError } from "../../api/client";
import { answerConsent, getPortal, type PortalView } from "../../api/portal";
import { Button } from "../../components/form/Button";
import { BrandMark, Icon, IconTile } from "../../components/Icon";
import { ErrorNotice } from "../../components/Notice";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge, type Tone } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { day } from "../../lib/format";
import { CONSENT_ANSWER, labelFor, MODE_LABELS } from "../../lib/labels";
import { languageLabel } from "../projects/choices";
import "./portal.css";
import { DataTable } from "../../components/DataTable";

const minutes = (m: number) =>
  m >= 60 ? `${(m / 60).toFixed(1)} h` : `${Math.round(m * 10) / 10} min`;
/** The session states the participant's page shows, as the server words them. */
const TONE: Record<string, Tone> = {
  Accepted: "success",
  "Recorded, being checked": "warning",
  Planned: "info",
  "Not used": "neutral",
};
/** The participant's own answer, in their words; the colours are the shared consent ones.
 * "Withdrew" only on answers from before D-129. */
const ANSWER: Record<string, string> = {
  GIVEN: "You agreed",
  REFUSED: "You did not agree",
  WITHDRAWN: "You withdrew your consent",
};
const yourAnswer = (status: string) => ({
  label: ANSWER[status] ?? labelFor({}, status),
  tone: CONSENT_ANSWER[status]?.tone ?? "neutral",
});

function Consent({
  view,
  token,
  onChange,
}: {
  view: PortalView;
  token: string | null; // null: the Super Admin's read-only view, no answer buttons
  onChange: (v: PortalView) => void;
}) {
  const [read, setRead] = useState(false);
  const { busy, error, run } = useAction();
  const answer = view.consent_status ? yourAnswer(view.consent_status) : undefined;
  const send = (decision: "GIVEN" | "REFUSED") =>
    void run(async () => {
      if (token) onChange(await answerConsent(token, decision));
    }, decision);

  return (
    <section className="card stack" aria-labelledby="consent-title">
      <div className="page-header">
        <h2 id="consent-title" className="with-icon">
          <IconTile name="verified" tone="green" size={28} />
          Consent form
        </h2>
        {answer ? (
          <StatusBadge tone={answer.tone} label={answer.label} />
        ) : (
          <StatusBadge tone="warning" label="Waiting for your answer" />
        )}
      </div>
      {view.consent_text.trim() ? (
        <>
          <div className="consent-text">{view.consent_text}</div>
          <p className="muted">Version {view.consent_policy_version}</p>
          {view.consent_status === "GIVEN" ? (
            <p className="notice notice--success" role="status">
              You agreed on {view.consent_at ? day(view.consent_at) : "this form"}.
            </p>
          ) : !token ? null : (
            <>
              {view.consent_at ? (
                <p className="muted">
                  Your answer was saved on {day(view.consent_at)}. You can still agree.
                </p>
              ) : null}
              <label className="checkbox">
                <input type="checkbox" checked={read} onChange={(e) => setRead(e.target.checked)} />
                I have read and understood this form
              </label>
              <p className="muted">
                If you agree, your answer is final: it cannot be changed later.
              </p>
              <div className="actions">
                <Button
                  busy={busy === "GIVEN"}
                  disabled={!read || busy !== null}
                  onClick={() => send("GIVEN")}
                >
                  <Icon name="check" size={16} weight="bold" />I agree
                </Button>
                {view.consent_status !== "REFUSED" ? (
                  <Button
                    variant="secondary"
                    busy={busy === "REFUSED"}
                    disabled={!read || busy !== null}
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

/** The participant's own details, minutes, consent and sessions. token null = read-only. */
export function ParticipantView({
  view,
  token,
  onChange,
}: {
  view: PortalView;
  token: string | null;
  onChange: (v: PortalView) => void;
}) {
  const details: [string, string][] = [
    ["Participant code", view.participant_code],
    ["Name", view.display_name],
    ["Language", languageLabel(view.language_code)],
    ...(view.dialect ? ([["Dialect", view.dialect]] as [string, string][]) : []),
    ["Phone", view.phone_hint ? `ending in ${view.phone_hint}` : "Not given"],
  ];
  return (
    <>
      <div className="portal__hero">
        <IconTile name="user" tone="blue" size={48} />
        <div>
          <h1>Your participation</h1>
          <p className="muted">
            {view.project_name} · participant {view.participant_code}
          </p>
        </div>
      </div>
      <section className="card" aria-labelledby="details-title">
        <h2 id="details-title">Your details</h2>
        <dl className="checks">
          {details.map(([label, value]) => (
            <div key={label} className="checks__row">
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <p className="muted">To correct your details, contact the project team.</p>
      </section>
      <div className="portal__stats">
        <div className="card">
          <p className="muted">Sessions</p>
          <p className="portal__num">{view.sessions.length}</p>
        </div>
        <div className="card">
          <p className="muted">Recorded time</p>
          <p className="portal__num">{minutes(view.recorded_minutes)}</p>
        </div>
        <div className="card">
          <p className="muted">Accepted recording time</p>
          <p className="portal__num">{minutes(view.accepted_minutes)}</p>
        </div>
        <div className="card">
          <p className="muted">Your share for payment</p>
          <p className="portal__num">{minutes(view.payable_minutes)}</p>
          <p className="muted">Half of each accepted conversation</p>
        </div>
      </div>
      <Consent view={view} token={token} onChange={onChange} />
      <section className="stack stack--tight" aria-labelledby="sessions-title">
        <h2 id="sessions-title">Your sessions</h2>
        {view.sessions.length === 0 ? (
          <EmptyState title="No sessions yet" message="Your recording sessions will appear here." />
        ) : (
          <DataTable>
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
              {view.sessions.map((s) => (
                <tr key={s.task_code}>
                  <td className="mono">{s.task_code}</td>
                  <td>{day(s.day)}</td>
                  <td>
                    <span className="cell-icon">
                      <Icon name={s.mode === "TELEPHONY" ? "phone" : "mic"} size={15} />
                      {labelFor(MODE_LABELS, s.mode)}
                    </span>
                  </td>
                  <td>{s.minutes === null ? "-" : minutes(s.minutes)}</td>
                  <td>
                    <StatusBadge tone={TONE[s.state] ?? "neutral"} label={s.state} />
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </section>
    </>
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
            <ParticipantView view={state.data} token={token} onChange={replace} />
            {state.data.link_expires_at ? (
              <p className="muted">
                This private link works until {day(state.data.link_expires_at)}. Do not share it. To
                ask a question or have your data removed, contact the project team.
              </p>
            ) : null}
          </div>
        ) : null}
      </main>
    </div>
  );
}

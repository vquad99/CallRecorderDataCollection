// A participant's personal page (D-067): opened from a private link, no account. Shows the
// participant's own details, minutes and sessions (read-only) and the project's consent form with
// their answer (D-100). The answer counts at once; "I agree" is final, with nothing to withdraw
// (D-129). Where the project takes signed forms and theirs is on file, the page says so and asks
// nothing (D-144). The same page, without the answer buttons, is the Super Admin's view.
import { useState } from "react";
import { useLocation } from "react-router";

import { ApiError } from "../../api/client";
import { answerConsent, getPortal, type PortalView } from "../../api/portal";
import { Figure, FigureLine } from "../../components/charts/Charts";
import { Button } from "../../components/form/Button";
import { BrandMark, Icon } from "../../components/Icon";
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
 * "Withdrew" only on answers from before D-129; "received" for a signed form staff uploaded. */
const ANSWER: Record<string, string> = {
  GIVEN: "You agreed",
  REFUSED: "You did not agree",
  WITHDRAWN: "You withdrew your consent",
  UPLOADED: "Signed form received",
};
const yourAnswer = (status: string) => ({
  label: ANSWER[status] ?? labelFor({}, status),
  tone: CONSENT_ANSWER[status]?.tone ?? "neutral",
});
/** Nothing left to answer: they agreed, or their signed form is on file. */
const settled = (status: PortalView["consent_status"]) =>
  status === "GIVEN" || status === "UPLOADED";

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
      {/* Its title and the answer on the section's title bar (D-158). */}
      <div className="card__head">
        <h2 id="consent-title">Consent form</h2>
        {answer ? (
          <StatusBadge tone={answer.tone} label={answer.label} />
        ) : (
          <StatusBadge tone="warning" label="Waiting for your answer" />
        )}
      </div>
      {view.consent_status === "UPLOADED" ? (
        // Their signed paper form is their consent here: nothing to answer online (D-144).
        <p className="notice notice--success" role="status">
          The project team has your signed consent form
          {view.consent_at ? ` (received on ${day(view.consent_at)})` : ""}.
        </p>
      ) : view.consent_text.trim() ? (
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
  // The consent email asks for an answer, so a form still to answer comes first, where a phone
  // shows it without scrolling; once settled it sits after the figures. Decided when the page
  // opens, so an answer just given stays in view (UXW-07).
  const [consentFirst] = useState(() => !settled(view.consent_status));
  const consentForm = <Consent view={view} token={token} onChange={onChange} />;
  return (
    <>
      <div className="portal__hero">
        <h1>Your participation</h1>
        <p className="muted">
          {view.project_name} · participant {view.participant_code}
        </p>
      </div>
      {consentFirst ? consentForm : null}
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
      {/* The key figures in one framed section, thin lines between them (D-158). */}
      <FigureLine label="Your figures">
        <Figure label="Sessions" value={String(view.sessions.length)} />
        <Figure label="Recorded time" value={minutes(view.recorded_minutes)} />
        <Figure label="Accepted recording time" value={minutes(view.accepted_minutes)} />
        <Figure
          label="Your share for payment"
          value={minutes(view.payable_minutes)}
          note="Half of each accepted conversation"
        />
      </FigureLine>
      {consentFirst ? null : consentForm}
      <section className="card stack stack--tight" aria-labelledby="sessions-title">
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

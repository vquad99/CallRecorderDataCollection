// Everything about one participant in one project (D-104), opened by "View" on the Participants
// page: profile, who added them, the projects they are in, their personal link, the consent form
// as they answered it, minutes, phone calls, and every session they were part of.
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { apiDownload, type ApiError } from "../../api/client";
import { CALL_STATE_LABELS, type CallState } from "../../api/telephony";
import * as work from "../../api/work";
import { Button } from "../../components/form/Button";
import { Icon, IconTile, type IconName } from "../../components/Icon";
import { ErrorNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { toApiError, useResource } from "../../hooks/useResource";
import "./participants.css";

const ANSWER_WORDS: Record<string, string> = {
  NONE: "Not answered",
  GIVEN: "Agreed",
  REFUSED: "Did not agree",
  WITHDRAWN: "Withdrew consent",
};
const ANSWER_TONE: Record<string, string> = {
  NONE: "DRAFT",
  GIVEN: "ACTIVE",
  REFUSED: "REJECTED",
  WITHDRAWN: "RETURNED",
};
const REVIEW_WORDS: Record<string, string> = {
  PENDING: "Waiting for review",
  APPROVED: "Approved",
  REJECTED: "Sent back",
};
const REVIEW_TONE: Record<string, string> = {
  PENDING: "ON_HOLD",
  APPROVED: "APPROVED",
  REJECTED: "REJECTED",
};
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "-");
const day = (iso: string) => new Date(iso).toLocaleDateString();
const words = (s: string) => s.toLowerCase().replace(/_/g, " ");
const minutes = (n: number) => `${n.toFixed(1)} min`;
const length = (seconds: number) =>
  seconds < 60 ? `${Math.round(seconds)} s` : `${(seconds / 60).toFixed(1)} min`;

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="checks__row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Block({ icon, title, children }: { icon: IconName; title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section className="pd-section" aria-labelledby={id}>
      <h3 id={id}>
        <Icon name={icon} size={18} />
        {title}
      </h3>
      {children}
    </section>
  );
}

function Work({ d }: { d: work.ParticipantDetails }) {
  const m = d.minutes;
  const c = d.calls;
  return (
    <Block icon="chart" title="Work in this project">
      <dl className="pd-tiles">
        <Fact label="Sessions">{d.sessions_total}</Fact>
        {m ? (
          <>
            <Fact label="Recorded conversations">{m.conversations}</Fact>
            <Fact label="Recorded minutes">{minutes(m.recorded_minutes)}</Fact>
            <Fact label="Approved conversations">{m.approved_conversations}</Fact>
            <Fact label="Approved minutes">{minutes(m.approved_minutes)}</Fact>
            <Fact label="Payable minutes">{minutes(m.payable_minutes)}</Fact>
          </>
        ) : null}
        <Fact label="Phone calls to them">{c ? c.total : 0}</Fact>
        {c ? (
          <>
            <Fact label="Calls with a recording">{c.recorded}</Fact>
            <Fact label="Last call">
              {c.last_state
                ? (CALL_STATE_LABELS[c.last_state as CallState] ?? words(c.last_state))
                : "-"}
              <small>{when(c.last_at)}</small>
            </Fact>
          </>
        ) : null}
      </dl>
    </Block>
  );
}

function Profile({ d }: { d: work.ParticipantDetails }) {
  const p = d.participant;
  return (
    <Block icon="id" title="Profile">
      <dl className="checks">
        <Fact label="Code">
          <span className="mono">{p.participant_code}</span>
        </Fact>
        <Fact label="Name">{p.display_label ?? "Hidden"}</Fact>
        <Fact label="Phone">{p.phone ?? (p.has_phone ? "On file (hidden)" : "None")}</Fact>
        <Fact label="Email">{p.email ?? (p.has_email ? "On file (hidden)" : "None")}</Fact>
        <Fact label="Language">
          {p.language_code}
          {p.dialect ? ` (${p.dialect})` : ""}
        </Fact>
        <Fact label="Added on">{when(p.created_at)}</Fact>
        <Fact label="Added by">{d.added_by ?? "-"}</Fact>
        <Fact label="Last changed">{when(d.updated_at)}</Fact>
        <Fact label="Projects">
          {d.projects.length > 0 ? d.projects.map((x) => `${x.code} · ${x.name}`).join(", ") : "-"}
        </Fact>
        <Fact label="Notes">{p.notes?.trim() ? p.notes : "None"}</Fact>
        {d.removed ? (
          <>
            <Fact label="Removed on">{when(d.removed.at)}</Fact>
            <Fact label="Removed by">{d.removed.by ?? "-"}</Fact>
            <Fact label="Reason for removal">{d.removed.reason ?? "-"}</Fact>
          </>
        ) : null}
      </dl>
    </Block>
  );
}

function PersonalLink({ link }: { link: work.ParticipantDetails["link"] }) {
  return (
    <Block icon="mail" title="Personal link">
      {link ? (
        <dl className="checks">
          <Fact label="State">{link.active ? "Working" : "Stopped or run out"}</Fact>
          <Fact label="Made on">{when(link.created_at)}</Fact>
          <Fact label="Made by">{link.created_by ?? "-"}</Fact>
          <Fact label="Works until">{when(link.expires_at)}</Fact>
          <Fact label="Last opened">{link.last_used_at ? when(link.last_used_at) : "Never"}</Fact>
          <Fact label="Given by">{link.handed_out ? "Staff passed it on" : "Email only"}</Fact>
        </dl>
      ) : (
        <p className="muted">No personal link has been made for this participant.</p>
      )}
    </Block>
  );
}

function ConsentForm({ form }: { form: work.ConsentFormView }) {
  const now = form.current;
  return (
    <Block icon="verified" title="Consent form">
      <dl className="checks">
        <Fact label="Answer">{now ? ANSWER_WORDS[now.status] : "Not answered yet"}</Fact>
        {now ? <Fact label="Answered on">{when(now.answered_at)}</Fact> : null}
        <Fact label="Form version">{form.form_version}</Fact>
        {now?.review_status ? (
          <Fact label="Review">
            {REVIEW_WORDS[now.review_status]}
            {now.review_note ? `: ${now.review_note}` : ""}
          </Fact>
        ) : null}
        {now?.reviewed_at ? <Fact label="Reviewed on">{when(now.reviewed_at)}</Fact> : null}
      </dl>
      <h4>{form.answered ? "Form text they answered" : "Form text they will see"}</h4>
      <div className="consent-doc">
        {form.form_text.trim() || "No consent form has been written for this project."}
      </div>
      {form.earlier.length > 0 ? (
        <>
          <h4>Earlier answers</h4>
          <ul className="list">
            {form.earlier.map((a) => (
              <li key={a.answered_at}>
                {when(a.answered_at)} · {ANSWER_WORDS[a.status]} · version {a.policy_version}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </Block>
  );
}

function Sessions({ d }: { d: work.ParticipantDetails }) {
  return (
    <Block icon="tasks" title="Sessions">
      {d.sessions.length === 0 ? (
        <p className="muted">This participant has not been part of a session yet.</p>
      ) : (
        <>
          <div className="table-wrap">
            <table className="table" aria-label="Sessions of this participant">
              <thead>
                <tr>
                  <th scope="col">Task</th>
                  <th scope="col">Type</th>
                  <th scope="col">Role</th>
                  <th scope="col">With</th>
                  <th scope="col">Moderator</th>
                  <th scope="col">Status</th>
                  <th scope="col">Consent in session</th>
                  <th scope="col">Recording</th>
                  <th scope="col">Calls</th>
                  <th scope="col">Created</th>
                </tr>
              </thead>
              <tbody>
                {d.sessions.map((s) => (
                  <tr key={s.task_id}>
                    <td className="mono">
                      <Link to={`/tasks/${s.task_id}`}>{s.task_code}</Link>
                    </td>
                    <td>{s.mode === "TELEPHONY" ? "Telephony" : "Face-to-face"}</td>
                    <td>Participant {s.slot}</td>
                    <td className="mono">{s.other_participant_code || "-"}</td>
                    <td>{s.moderator ?? <span className="muted">Nobody yet</span>}</td>
                    <td>
                      <StatusBadge
                        status={s.status}
                        label={work.TASK_STATUS_LABELS[s.status] ?? words(s.status)}
                      />
                    </td>
                    <td>
                      {s.consent_status ? (
                        <>
                          <StatusBadge
                            status={ANSWER_TONE[s.consent_status] ?? "DRAFT"}
                            label={ANSWER_WORDS[s.consent_status] ?? words(s.consent_status)}
                          />
                          <div className="muted">
                            {s.consent_method ? `${words(s.consent_method)} · ` : ""}
                            {when(s.consent_at)}
                          </div>
                        </>
                      ) : (
                        <span className="muted">Not noted</span>
                      )}
                    </td>
                    <td>
                      {s.recordings > 0 ? (
                        <>
                          {s.recording_seconds !== null ? length(s.recording_seconds) : "Recorded"}
                          {s.recordings > 1 ? ` (${s.recordings} recordings)` : ""}
                          <div className="muted">{when(s.recorded_at)}</div>
                        </>
                      ) : (
                        <span className="muted">None</span>
                      )}
                    </td>
                    <td>{s.mode === "TELEPHONY" ? s.phone_calls : "-"}</td>
                    <td>{when(s.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {d.sessions_total > d.sessions.length ? (
            <p className="muted">
              Showing the newest {d.sessions.length} of {d.sessions_total} sessions.
            </p>
          ) : null}
        </>
      )}
    </Block>
  );
}

function Head({
  d,
  onDownload,
  onClose,
}: {
  d: work.ParticipantDetails;
  onDownload: (() => void) | null;
  onClose: () => void;
}) {
  const p = d.participant;
  return (
    <div className="pd-head">
      <IconTile name="user" tone="blue" size={46} />
      <div className="pd-head__text">
        <h2>
          {p.participant_code}
          {p.display_label ? ` · ${p.display_label}` : ""}
        </h2>
        <p className="muted">
          {p.language_code}
          {p.dialect ? ` (${p.dialect})` : ""} · in the project since {day(p.created_at)}
        </p>
        <div className="pd-head__badges">
          {d.removed ? <StatusBadge status="REJECTED" label="Removed" /> : null}
          {p.consent_status ? (
            <StatusBadge
              status={ANSWER_TONE[p.consent_status] ?? "DRAFT"}
              label={`Consent form: ${ANSWER_WORDS[p.consent_status] ?? words(p.consent_status)}`}
            />
          ) : null}
          {p.consent_status === "GIVEN" && p.consent_review ? (
            <StatusBadge
              status={REVIEW_TONE[p.consent_review] ?? "DRAFT"}
              label={REVIEW_WORDS[p.consent_review] ?? words(p.consent_review)}
            />
          ) : null}
          {d.link ? (
            <StatusBadge
              status={d.link.active ? "ACTIVE" : "DRAFT"}
              label={d.link.active ? "Personal link working" : "Personal link stopped"}
            />
          ) : null}
        </div>
      </div>
      <div className="actions">
        {onDownload ? (
          <Button variant="secondary" onClick={onDownload}>
            <Icon name="upload" size={15} />
            Download consent form
          </Button>
        ) : null}
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      </div>
    </div>
  );
}

export function ParticipantDetailsPanel({
  projectId,
  participantId,
  onClose,
}: {
  projectId: string;
  participantId: string;
  onClose: () => void;
}) {
  const { state, reload } = useResource(
    () => work.participantDetails(projectId, participantId),
    [projectId, participantId],
  );
  const [error, setError] = useState<ApiError | null>(null);
  const form = state.status === "loaded" ? state.data.consent_form : null;
  // The panel opens under the table: bring it into view once it has its content.
  const panel = useRef<HTMLElement>(null);
  const loaded = state.status === "loaded";
  useEffect(() => {
    const el = panel.current;
    if (loaded && el && "scrollIntoView" in el) {
      el.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }, [loaded]);
  return (
    <section ref={panel} className="card stack pd" aria-label="Participant details">
      {state.status === "loading" ? <LoadingState label="Loading the participant" /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        <>
          <Head
            d={state.data}
            onClose={onClose}
            onDownload={
              form
                ? () =>
                    void apiDownload(
                      work.consentFormFileUrl(projectId, participantId),
                      `consent_${form.project_code}_${form.participant_code}.html`,
                    ).catch((err: unknown) => setError(toApiError(err)))
                : null
            }
          />
          <ErrorNotice error={error} />
          <Work d={state.data} />
          <Profile d={state.data} />
          <PersonalLink link={state.data.link} />
          {form ? <ConsentForm form={form} /> : null}
          <Sessions d={state.data} />
        </>
      ) : null}
    </section>
  );
}

// Everything about one participant in one project (D-104), opened by "View": profile, who added
// them, the projects they are in, their personal link, the consent form as they answered it,
// minutes, phone calls, and every session they were part of.
import { useId, type ReactNode } from "react";
import { Link } from "react-router";

import { apiDownload } from "../../api/client";
import { CALL_STATE_LABELS } from "../../api/telephony";
import * as work from "../../api/work";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Icon, IconTile, type IconName } from "../../components/Icon";
import { ErrorNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { day, duration, when } from "../../lib/format";
import { consentAnswer, labelFor, MODE_LABELS, TASK_STATUS_LABELS } from "../../lib/labels";
import { languageLabel } from "../projects/choices";
import "./participants.css";

const minutes = (n: number) => `${n.toFixed(1)} min`;
const language = (p: work.Participant) =>
  `${languageLabel(p.language_code)}${p.dialect ? `, ${p.dialect}` : ""}`;

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
              {c.last_state ? labelFor(CALL_STATE_LABELS, c.last_state) : "-"}
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
        <Fact label="Language">{language(p)}</Fact>
        {p.district ? <Fact label="District">{p.district}</Fact> : null}
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
        <Fact label="Answer">{now ? consentAnswer(now.status).label : "No answer yet"}</Fact>
        {now ? <Fact label="Answered on">{when(now.answered_at)}</Fact> : null}
        <Fact label="Form version">{form.form_version}</Fact>
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
                {when(a.answered_at)} · {consentAnswer(a.status).label} · version {a.policy_version}
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
          <DataTable label="Sessions of this participant">
            <thead>
              <tr>
                <th scope="col">Task</th>
                <th scope="col">Recording type</th>
                <th scope="col">Role</th>
                <th scope="col">With</th>
                <th scope="col">Moderator</th>
                <th scope="col">Status</th>
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
                  <td>{labelFor(MODE_LABELS, s.mode)}</td>
                  <td>Participant {s.slot}</td>
                  <td className="mono">{s.other_participant_code || "-"}</td>
                  <td>{s.moderator ?? <span className="muted">Nobody yet</span>}</td>
                  <td>
                    <StatusBadge status={s.status} label={labelFor(TASK_STATUS_LABELS, s.status)} />
                  </td>
                  <td>
                    {s.recordings > 0 ? (
                      <>
                        {s.recording_seconds !== null ? duration(s.recording_seconds) : "Recorded"}
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
          </DataTable>
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

function Head({ d, onDownload }: { d: work.ParticipantDetails; onDownload: (() => void) | null }) {
  const p = d.participant;
  const answer = p.consent_status ? consentAnswer(p.consent_status) : null;
  return (
    <div className="pd-head">
      <IconTile name="user" size={46} />
      <div className="pd-head__text">
        <h3>
          {p.participant_code}
          {p.display_label ? ` · ${p.display_label}` : ""}
        </h3>
        <p className="muted">
          {language(p)} · in the project since {day(p.created_at)}
        </p>
        <div className="pd-head__badges">
          {d.removed ? <StatusBadge tone="danger" label="Removed" /> : null}
          {answer ? (
            <StatusBadge tone={answer.tone} label={`Consent form: ${answer.label}`} />
          ) : null}
          {d.link ? (
            <StatusBadge
              tone={d.link.active ? "success" : "neutral"}
              label={d.link.active ? "Personal link working" : "Personal link stopped"}
            />
          ) : null}
        </div>
      </div>
      {onDownload ? (
        <div className="actions">
          <Button variant="secondary" icon="fileText" onClick={onDownload}>
            Download consent form
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function ParticipantDetails({
  projectId,
  participantId,
}: {
  projectId: string;
  participantId: string;
}) {
  const { state, reload } = useResource(
    () => work.participantDetails(projectId, participantId),
    [projectId, participantId],
  );
  const { error, run } = useAction();
  if (state.status === "loading") return <LoadingState label="Loading the participant" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  const d = state.data;
  const form = d.consent_form;
  return (
    <div className="stack pd">
      <Head
        d={d}
        onDownload={
          form
            ? () =>
                void run(() =>
                  apiDownload(
                    work.consentFormFileUrl(projectId, participantId),
                    `consent_${form.project_code}_${form.participant_code}.html`,
                  ),
                )
            : null
        }
      />
      <ErrorNotice error={error} />
      <Work d={d} />
      <Profile d={d} />
      <PersonalLink link={d.link} />
      {form ? <ConsentForm form={form} /> : null}
      <Sessions d={d} />
    </div>
  );
}

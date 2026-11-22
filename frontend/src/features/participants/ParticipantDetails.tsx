// Everything about one participant in one project (D-104), opened by "View": profile, who added
// them, the projects they are in, their personal link, the consent form as they answered it, their
// uploaded documents (D-144), minutes, phone calls, and every session they were part of. Laid out
// as key / value tables in two columns, the sessions as one table under them (D-152).
import { useId, type ReactNode } from "react";
import { Link } from "react-router";

import { apiDownload } from "../../api/client";
import type { ConsentMode } from "../../api/projects";
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
import {
  consentAnswer,
  FORM_MISSING,
  labelFor,
  MODE_LABELS,
  TASK_STATUS_LABELS,
} from "../../lib/labels";
import {
  EDUCATION_LABELS,
  EDUCATION_MEDIUM_LABELS,
  GENDER_LABELS,
  missingSpeakerDetails,
  placeText,
  SPEAKER_FIELDS,
  speakerDetailsOf,
} from "../../lib/speakers";
import { languageLabel } from "../projects/choices";
import { DocumentBadges, DocumentsPanel } from "./Documents";
import "./participants.css";

const minutes = (n: number) => `${n.toFixed(1)} min`;

/** A participant without the speaker details the project needs cannot be put on a task yet
 * (D-143, D-145); the server says so in `speaker_details_complete`. */
export function DetailsMissing() {
  return (
    <span title="Some speaker details this project needs are missing: add them with Edit before making a task.">
      <StatusBadge tone="warning" label="Details missing" />
    </span>
  );
}
const language = (p: work.Participant) =>
  `${languageLabel(p.language_code)}${p.dialect ? `, ${p.dialect}` : ""}`;

/** One line of a key / value table (D-152): the label on the left, the value on the right. */
function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="pd-kv__row">
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
      <dl className="pd-kv pd-kv--figures">
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

function Profile({ d, required }: { d: work.ParticipantDetails; required: readonly string[] }) {
  const p = d.participant;
  const missing = missingSpeakerDetails(
    { ...speakerDetailsOf(p), district: p.district ?? "" },
    required,
  );
  const education = [
    p.education ? labelFor(EDUCATION_LABELS, p.education) : null,
    p.education_medium ? `${labelFor(EDUCATION_MEDIUM_LABELS, p.education_medium)} medium` : null,
  ]
    .filter(Boolean)
    .join(", ");
  return (
    <Block icon="id" title="Profile">
      <dl className="pd-kv">
        <Fact label="Code">
          <span className="mono">{p.participant_code}</span>
        </Fact>
        <Fact label="Name">{p.display_label ?? "Hidden"}</Fact>
        <Fact label="Phone">{p.phone ?? (p.has_phone ? "On file (hidden)" : "None")}</Fact>
        <Fact label="Email">{p.email ?? (p.has_email ? "On file (hidden)" : "None")}</Fact>
        <Fact label="Language">{language(p)}</Fact>
        {/* Speaker details (D-143). */}
        <Fact label="Speaker details">
          {p.speaker_details_complete || missing.length === 0
            ? "Complete"
            : `Missing: ${missing.join(", ")}`}
        </Fact>
        <Fact label="Age">{p.age ?? "-"}</Fact>
        <Fact label="Gender">{p.gender ? labelFor(GENDER_LABELS, p.gender) : "-"}</Fact>
        <Fact label="Lives in">
          {placeText(p.current_state, p.current_district, p.current_pincode)}
        </Fact>
        <Fact label="Native place">{placeText(p.native_state, p.district, p.native_pincode)}</Fact>
        <Fact label="Native language">{p.native_language ?? "-"}</Fact>
        <Fact label="Education">{education || "-"}</Fact>
        <Fact label="Recorded in">
          {placeText(p.recording_state, p.recording_district, p.recording_pincode)}
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
        <dl className="pd-kv">
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
      <dl className="pd-kv">
        <Fact label="Answer">{now ? consentAnswer(now.status).label : "No answer yet"}</Fact>
        {now ? <Fact label="Answered on">{when(now.answered_at)}</Fact> : null}
        <Fact label="Form version">{form.form_version}</Fact>
        {form.earlier.length > 0 ? (
          <Fact label="Earlier answers">
            <ul className="pd-earlier">
              {form.earlier.map((a) => (
                <li key={a.answered_at}>
                  {when(a.answered_at)} · {consentAnswer(a.status).label} · version{" "}
                  {a.policy_version}
                </li>
              ))}
            </ul>
          </Fact>
        ) : null}
      </dl>
      {/* The form's text is long: closed until someone opens it (D-152). */}
      <details className="pd-more">
        <summary>{form.answered ? "Form text they answered" : "Form text they will see"}</summary>
        <div className="consent-doc">
          {form.form_text.trim() || "No consent form has been written for this project."}
        </div>
      </details>
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

/** The consent badge's words: "Consent form: Agreed" online, "Consent: Form uploaded" or
 * "Consent form missing" where the project takes signed forms (D-144). */
function consentBadge(status: string | null, mode: ConsentMode | undefined): string | null {
  if (!status) return null;
  const { label } = consentAnswer(status, mode);
  if (label === FORM_MISSING.label) return label;
  return mode === "UPLOAD" ? `Consent: ${label}` : `Consent form: ${label}`;
}

function Head({
  d,
  mode,
  onDownload,
}: {
  d: work.ParticipantDetails;
  mode: ConsentMode | undefined;
  onDownload: (() => void) | null;
}) {
  const p = d.participant;
  const answer = p.consent_status ? consentAnswer(p.consent_status, mode) : null;
  const badge = consentBadge(p.consent_status, mode);
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
          {!d.removed && p.speaker_details_complete === false ? <DetailsMissing /> : null}
          {answer && badge ? <StatusBadge tone={answer.tone} label={badge} /> : null}
          {!d.removed ? (
            <DocumentBadges p={p} mode={mode} consent={badge !== FORM_MISSING.label} />
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

const EVERY_DETAIL = SPEAKER_FIELDS.map((f) => f.key);

export function ParticipantDetails({
  projectId,
  participantId,
  consentMode,
  required = EVERY_DETAIL,
}: {
  projectId: string;
  participantId: string;
  /** The project's way of consent (D-144), for the consent badge's words. */
  consentMode?: ConsentMode | undefined;
  /** The speaker details the project needs (D-145), for the words on what is missing. */
  required?: readonly string[];
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
        mode={consentMode}
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
      {/* D-152: two columns on a wide window, who they are on the left and their work, link,
          consent and documents on the right; the sessions under both. One column on a phone. */}
      <div className="pd-grid">
        <div className="pd-col">
          <Profile d={d} required={required} />
        </div>
        <div className="pd-col">
          <Work d={d} />
          <PersonalLink link={d.link} />
          {form ? <ConsentForm form={form} /> : null}
          {/* D-144: the signed consent form and the address proof, as in the Documents window. */}
          <Block icon="fileText" title="Documents">
            <DocumentsPanel
              projectId={projectId}
              participantId={participantId}
              onChanged={reload}
            />
          </Block>
        </div>
      </div>
      <Sessions d={d} />
    </div>
  );
}

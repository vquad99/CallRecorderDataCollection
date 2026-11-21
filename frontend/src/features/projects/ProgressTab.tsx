// A project's Progress tab (D-148): what was collected against the project's targets. Completed
// minutes (effective speech or the full length, as the project's rules say), conversations and
// speakers, and the shares by age band, gender, recording type and district with their variance.
// For the people who manage the project, like the other tabs (D-104). Loaded with the tab, not
// with the first screen.
import { useId, type ReactNode } from "react";

import { getProgress, type ProjectProgress, type Share } from "../../api/progress";
import { Stat } from "../../components/charts/Charts";
import { DataTable } from "../../components/DataTable";
import { IconTile, type IconName } from "../../components/Icon";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useResource } from "../../hooks/useResource";
import { useProject } from "./ProjectDetailPage";
import "./progress.css";

/** A length for people: "6 h 12 min", "45 min", "30 s". */
export function spokenLength(ms: number): string {
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

const number = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));
/** A percent: "40 %", "12.5 %". */
const pct = (n: number) => `${number(n)} %`;
/** A variance in percentage points: "+4 %", "−6 %", "0 %". */
export const variance = (n: number) =>
  n > 0 ? `+${number(n)} %` : n < 0 ? `−${number(-n)} %` : "0 %";
/** A ring's value: a whole percent from 0 to 100. */
const ring = (n: number | null) => (n === null ? undefined : Math.min(100, Math.round(n)));
const of = (count: number, target: number | null) =>
  target === null ? String(count) : `${count} / ${target}`;

function Card({ icon, title, children }: { icon: IconName; title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section className="card stack stack--tight" aria-labelledby={id}>
      <h2 id={id} className="with-icon">
        <IconTile name={icon} size={28} />
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="checks__row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

const BASIS = {
  speakers: (n: number) =>
    `Percent of the ${n} speaker${n === 1 ? "" : "s"} with an approved conversation.`,
  conversations: (n: number) => `Percent of the ${n} approved conversation${n === 1 ? "" : "s"}.`,
};

/** One share: actual count and percent against the target percent, and the variance. */
function ShareTable({
  icon,
  title,
  share,
  noTarget,
}: {
  icon: IconName;
  title: string;
  share: Share;
  noTarget: string;
}) {
  return (
    <Card icon={icon} title={title}>
      <p className="muted">
        {share.total === 0 ? `No approved conversations yet.` : BASIS[share.basis](share.total)}
        {share.has_target ? "" : ` ${noTarget}`}
      </p>
      {share.rows.length === 0 || share.total === 0 ? null : (
        <DataTable label={title}>
          <thead>
            <tr>
              <th scope="col">Group</th>
              <th scope="col" className="num">
                Count
              </th>
              <th scope="col">Actual</th>
              <th scope="col" className="num">
                Target
              </th>
              <th scope="col" className="num">
                Variance
              </th>
            </tr>
          </thead>
          <tbody>
            {share.rows.map((r) => (
              <tr key={r.key}>
                <td>{r.label}</td>
                <td className="num">{r.count}</td>
                <td>
                  <span className="share-bar">
                    <span className="share-bar__track" aria-hidden="true">
                      <span style={{ width: `${Math.min(100, r.percent)}%` }} />
                      {r.target_percent !== null ? (
                        <span
                          className="share-bar__target"
                          style={{ left: `${Math.min(100, r.target_percent)}%` }}
                        />
                      ) : null}
                    </span>
                    {pct(r.percent)}
                  </span>
                </td>
                <td className="num">{r.target_percent === null ? "-" : pct(r.target_percent)}</td>
                <td className="num">
                  {r.variance === null ? (
                    "-"
                  ) : (
                    <span className={r.variance < 0 ? "variance variance--below" : "variance"}>
                      {variance(r.variance)}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
    </Card>
  );
}

function Body({ data }: { data: ProjectProgress }) {
  const done = data.completed;
  const effective = done.counts === "EFFECTIVE";
  const counted = effective ? "effective speech" : "full length";
  const talks = data.conversations;
  const people = data.speakers;
  const targetMs = done.target_hours === null ? null : done.target_hours * 3_600_000;
  return (
    <div className="stack">
      {talks.approved === 0 ? (
        <p className="notice notice--info">
          No approved conversations yet: the figures fill in as conversations are approved.
        </p>
      ) : null}
      <div className="stats">
        <Stat
          icon="verified"
          label="Completed"
          value={spokenLength(done.completed_ms)}
          note={
            targetMs === null
              ? `${counted} of approved conversations; no hours target`
              : `of ${spokenLength(targetMs)}, ${counted} of approved conversations`
          }
          ring={ring(done.percent_of_target)}
        />
        <Stat
          icon="tasks"
          label="Approved conversations"
          value={of(talks.approved, talks.target)}
          note={talks.target === null ? "no target" : "approved of the target"}
          ring={ring(talks.percent_of_target)}
        />
        <Stat
          icon="people"
          label="Speakers"
          value={of(people.with_approved, people.target)}
          note="with an approved conversation"
          ring={ring(people.percent_of_target)}
        />
        <Stat
          icon="waveform"
          label="Effective speech"
          value={done.effective_share_pct === null ? "-" : pct(done.effective_share_pct)}
          note="of the recorded audio"
        />
      </div>

      <Card icon="verified" title="Completed">
        {targetMs !== null ? (
          <div className="progress-line">
            <progress
              max={100}
              value={Math.min(100, done.percent_of_target ?? 0)}
              aria-label="Completed of the hours target"
            />
            <span>
              {spokenLength(done.completed_ms)} of {spokenLength(targetMs)} (
              {pct(done.percent_of_target ?? 0)})
            </span>
          </div>
        ) : (
          <p className="muted">No hours target: set one on the Rules tab.</p>
        )}
        <dl className="checks">
          <Row label="Approved conversations" value={String(done.approved_conversations)} />
          <Row label="Their full length" value={spokenLength(done.approved_ms)} />
          <Row label="Their effective speech" value={spokenLength(done.approved_effective_ms)} />
          {done.not_measured > 0 ? (
            <Row
              label="Effective speech not measured yet"
              value={`${done.not_measured} conversation${done.not_measured === 1 ? "" : "s"}`}
            />
          ) : null}
          <Row
            label="Recorded, not yet approved"
            value={`${done.recorded_conversations} (${spokenLength(done.recorded_ms)}, ${spokenLength(done.recorded_effective_ms)} effective)`}
          />
        </dl>
        <p className="muted">
          Completed counts the {counted} of approved conversations, as the project&apos;s rules say
          (Rules tab, Audio and progress).
          {done.not_measured > 0
            ? " A conversation whose effective speech is not measured yet counts as none until it is (shortly after it was made)."
            : ""}
        </p>
      </Card>

      <div className="split">
        <Card icon="tasks" title="Conversations">
          <dl className="checks">
            <Row label="Approved" value={of(talks.approved, talks.target)} />
            <Row label="Waiting for QC or approval" value={String(talks.waiting_qc)} />
            <Row label="In progress" value={String(talks.in_progress)} />
            <Row label="Not started" value={String(talks.not_started)} />
            <Row label="Rejected" value={String(talks.rejected)} />
            <Row label="Cancelled" value={String(talks.cancelled)} />
          </dl>
        </Card>
        <Card icon="people" title="Speakers">
          <dl className="checks">
            <Row
              label="With an approved conversation"
              value={of(people.with_approved, people.target)}
            />
            <Row label="Registered in the project" value={String(people.registered)} />
            <Row
              label={
                people.limit === null
                  ? "Conversations per speaker"
                  : `Reached the limit of ${people.limit} conversations`
              }
              value={people.at_limit === null ? "No limit" : String(people.at_limit)}
            />
          </dl>
        </Card>
      </div>

      <div className="split">
        <ShareTable
          icon="people"
          title="Age bands"
          share={data.age_bands}
          noTarget="No age bands set: add them on the Rules tab."
        />
        <ShareTable
          icon="user"
          title="Gender"
          share={data.gender}
          noTarget="No gender target set."
        />
        <ShareTable
          icon="phone"
          title="Face-to-face and phone"
          share={data.modes}
          noTarget="No target set."
        />
        <ShareTable
          icon="target"
          title="Districts"
          share={data.districts}
          noTarget="No districts listed: the speakers' own native districts."
        />
      </div>

      <Card icon="info" title="How these are counted">
        <dl className="definitions">
          <dt>Effective speech</dt>
          <dd>
            The time someone speaks in a recording: silence (quieter than −50 dBFS on every channel)
            is left out; gaps under 0.3 s between words count as speech and a sound under 0.1 s on
            its own (a click) does not. Measured by level, so loud background noise counts as
            speech; QC listens for noise.
          </dd>
          <dt>Long pauses</dt>
          <dd>
            Silences inside the conversation longer than {data.pause_limit_seconds} s (the
            project&apos;s limit). The automatic check counts them.
          </dd>
          <dt>Speakers and shares</dt>
          <dd>
            Age bands, gender and districts are shares of the speakers with at least one approved
            conversation, each counted once, with their details as they are now (district: native
            district). Face-to-face and phone are shares of the approved conversations. People
            without a detail are under “Not given”.
          </dd>
          <dt>Variance</dt>
          <dd>
            The actual percent minus the target percent: +4 % is above the target, −6 % below.
          </dd>
        </dl>
      </Card>
    </div>
  );
}

export function ProgressTab() {
  const { project } = useProject();
  const { state, reload } = useResource(() => getProgress(project.id), [project.id]);
  if (state.status === "loading") return <LoadingState label="Loading progress" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  return <Body data={state.data} />;
}

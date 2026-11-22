// A project's Progress tab (D-148, laid out as one dashboard in D-151): what was collected against
// the project's targets. The key figures in one strip (completed hours, approved conversations,
// speakers, effective speech); the shares by age band, gender, recording type and district in one
// balance table against their targets; the conversations by status; the definitions folded away.
// For the people who manage the project, like the other tabs (D-104). Loaded with the tab, not
// with the first screen.
import { getProgress, type ProjectProgress, type Share, type ShareRow } from "../../api/progress";
import {
  CellBar,
  Donut,
  KeyTable,
  Kpi,
  KpiStrip,
  MatrixTable,
  Panel,
  TargetBar,
  type MatrixSection,
} from "../../components/charts/Charts";
import { STAGES } from "../../components/charts/stages";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useFirstRows } from "../../hooks/useFirstRows";
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
/** A bar to a target, when there is one. */
const toTarget = (percent: number | null, label: string) =>
  percent === null ? undefined : { percent, label, text: pct(percent) };

const BASIS = {
  speakers: (n: number) =>
    `Percent of the ${n} speaker${n === 1 ? "" : "s"} with an approved conversation.`,
  conversations: (n: number) => `Percent of the ${n} approved conversation${n === 1 ? "" : "s"}.`,
};

/** Districts shown before "Show all": the client's list has eight. */
const FIRST_DISTRICTS = 10;

interface Group {
  key: string;
  title: string;
  share: Share;
  noTarget: string;
}

/** Every share in one table: a section per group, the actual count and percent against the
 * target percent, the variance, and a bar with a tick at the target. */
function BalanceMatrix({ data }: { data: ProjectProgress }) {
  const districts = useFirstRows(data.districts.rows, FIRST_DISTRICTS);
  const groups: Group[] = [
    {
      key: "age",
      title: "Age bands",
      share: data.age_bands,
      noTarget: "No age bands set: add them on the Rules tab.",
    },
    { key: "gender", title: "Gender", share: data.gender, noTarget: "No gender target set." },
    {
      key: "modes",
      title: "Face-to-face and phone",
      share: data.modes,
      noTarget: "No target set.",
    },
    {
      key: "districts",
      title: "Districts",
      share: { ...data.districts, rows: districts.shown },
      noTarget: "No districts listed: the speakers' own native districts.",
    },
  ];
  // Each section's bars on its own scale (12.5 % of eight districts would be a sliver of 100).
  const scale = new Map(
    groups.map((g) => [
      g.key,
      Math.min(
        100,
        1.1 * Math.max(1, ...g.share.rows.map((r) => Math.max(r.percent, r.target_percent ?? 0))),
      ),
    ]),
  );
  const sections: MatrixSection<ShareRow & { group: string }>[] = groups.map((g) => ({
    key: g.key,
    title: g.title,
    note: `${g.share.total === 0 ? "No approved conversations yet." : BASIS[g.share.basis](g.share.total)}${g.share.has_target ? "" : ` ${g.noTarget}`}`,
    rows: g.share.total === 0 ? [] : g.share.rows.map((r) => ({ ...r, group: g.key })),
  }));
  return (
    <>
      <MatrixTable
        label="Balance against the targets"
        head="Group"
        groups={[
          { label: "Actual", span: 3, tone: "blue" },
          { label: "Target", span: 2, tone: "teal" },
        ]}
        columns={[
          { key: "count", label: "Count", num: true, cell: (r) => r.count },
          { key: "percent", label: "Share", num: true, cell: (r) => pct(r.percent) },
          {
            key: "bar",
            label: <span className="sr-only">Share against the target</span>,
            cell: (r) => (
              <TargetBar
                value={r.percent}
                target={r.target_percent}
                max={scale.get(r.group) ?? 100}
              />
            ),
          },
          {
            key: "target",
            label: "Share",
            num: true,
            cell: (r) => (r.target_percent === null ? "-" : pct(r.target_percent)),
          },
          {
            key: "variance",
            label: "Variance",
            num: true,
            cell: (r) =>
              r.variance === null ? (
                "-"
              ) : (
                <span
                  className={
                    r.variance < 0
                      ? "variance variance--below"
                      : r.variance > 0
                        ? "variance variance--above"
                        : "variance"
                  }
                >
                  {variance(r.variance)}
                </span>
              ),
          },
        ]}
        sections={sections}
        rowKey={(r) => r.key}
        rowLabel={(r) => r.label}
      />
      {districts.more}
    </>
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
    <div className="dash progress">
      {talks.approved === 0 ? (
        <p className="notice notice--info">
          No approved conversations yet: the figures fill in as conversations are approved.
        </p>
      ) : null}
      <KpiStrip label="Against the targets">
        <Kpi
          icon="verified"
          label="Completed"
          value={spokenLength(done.completed_ms)}
          of={targetMs === null ? undefined : `of ${spokenLength(targetMs)}`}
          meter={toTarget(done.percent_of_target, "Completed of the hours target")}
          note={
            targetMs === null
              ? "No hours target: set one on the Rules tab."
              : `${counted} of approved conversations`
          }
        />
        <Kpi
          icon="tasks"
          label="Approved conversations"
          value={String(talks.approved)}
          of={talks.target === null ? undefined : `/ ${talks.target}`}
          meter={toTarget(talks.percent_of_target, "Approved conversations of the target")}
          note={talks.target === null ? "No target set." : undefined}
        />
        <Kpi
          icon="people"
          label="Speakers"
          value={String(people.with_approved)}
          of={people.target === null ? undefined : `/ ${people.target}`}
          meter={toTarget(people.percent_of_target, "Speakers of the target")}
          note="with an approved conversation"
        />
        <Kpi
          icon="waveform"
          label="Effective speech"
          value={done.effective_share_pct === null ? "-" : pct(done.effective_share_pct)}
          note="of the recorded audio"
        />
      </KpiStrip>

      <div className="dash-grid">
        <Panel
          className="g-8"
          icon="target"
          title="Balance against the targets"
          action="Variance: actual minus target"
        >
          <BalanceMatrix data={data} />
        </Panel>
        <div className="dash-col g-4">
          <Panel icon="tasks" title="Conversations">
            <Donut
              label="Conversations by status"
              unit="tasks"
              emptyText="No conversations yet."
              parts={STAGES.map((s) => ({
                key: s.key,
                label: s.label,
                n: talks[s.key],
                color: s.color,
              }))}
            />
          </Panel>
          <Panel icon="verified" title="Completed">
            <MatrixTable<{ key: string; label: string; value: string }>
              label="Completed"
              head="Conversations"
              quietHead
              columns={[{ key: "value", label: "Amount", num: true, cell: (r) => r.value }]}
              sections={[
                {
                  key: "approved",
                  title: "Approved",
                  rows: [
                    {
                      key: "n",
                      label: "Conversations",
                      value: String(done.approved_conversations),
                    },
                    { key: "full", label: "Full length", value: spokenLength(done.approved_ms) },
                    {
                      key: "effective",
                      label: "Effective speech",
                      value: spokenLength(done.approved_effective_ms),
                    },
                  ],
                },
                {
                  key: "recorded",
                  title: "Recorded, not yet approved",
                  rows: [
                    {
                      key: "n",
                      label: "Conversations",
                      value: String(done.recorded_conversations),
                    },
                    { key: "full", label: "Full length", value: spokenLength(done.recorded_ms) },
                    {
                      key: "effective",
                      label: "Effective speech",
                      value: spokenLength(done.recorded_effective_ms),
                    },
                  ],
                },
              ]}
              rowKey={(r) => r.key}
              rowLabel={(r) => r.label}
            />
            {done.not_measured > 0 ? (
              <p className="muted">
                {done.not_measured} approved conversation{done.not_measured === 1 ? " is" : "s are"}{" "}
                not measured yet: each counts as none until it is (shortly after it was made).
              </p>
            ) : null}
          </Panel>
          <Panel icon="people" title="Speakers">
            <KeyTable
              label="Speakers"
              rows={[
                {
                  label: "With an approved conversation",
                  value:
                    people.target === null
                      ? String(people.with_approved)
                      : `${people.with_approved} / ${people.target}`,
                },
                { label: "Registered in the project", value: people.registered },
                {
                  label:
                    people.limit === null
                      ? "Conversations per speaker"
                      : `Reached the limit of ${people.limit} conversations`,
                  value:
                    people.at_limit === null ? (
                      "No limit"
                    ) : (
                      <CellBar value={people.at_limit} max={people.registered}>
                        {people.at_limit}
                      </CellBar>
                    ),
                },
              ]}
            />
          </Panel>
        </div>
      </div>

      <details className="dash-notes">
        <summary>How these are counted</summary>
        <dl className="definitions">
          <dt>Effective speech</dt>
          <dd>
            The time someone speaks in a recording: silence (quieter than −50 dBFS on every channel)
            is left out; gaps under 0.3 s between words count as speech and a sound under 0.1 s on
            its own (a click) does not. Measured by level, so loud background noise counts as
            speech; QC listens for noise.
          </dd>
          <dt>Completed</dt>
          <dd>
            The {counted} of the approved conversations, as the project&apos;s rules say (Rules tab,
            Audio and progress).
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
            without a detail are under “Not given”. Each section&apos;s bars have their own scale;
            the tick is the target.
          </dd>
          <dt>Variance</dt>
          <dd>
            The actual percent minus the target percent: +4 % is above the target, −6 % below.
          </dd>
        </dl>
      </details>
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

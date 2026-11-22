// Dashboard (DASH-001..006). One page, three views decided by the server: a client sees collection
// progress only; moderators and QC see their own work; managers also see what needs attention.
// Laid out as one screen (D-151): the key figures in one strip, then a grid of charts and tables.
import { Link } from "react-router";
import { useState } from "react";

import { getDashboard, type Dashboard, type DashboardFilters } from "../../api/dashboard";
import {
  CellBar,
  DayChart,
  Donut,
  KeyTable,
  Kpi,
  KpiStrip,
  Panel,
  SplitBar,
} from "../../components/charts/Charts";
import { stageParts } from "../../components/charts/stages";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Avatar, Icon, type IconName, IconTile } from "../../components/Icon";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useFirstRows } from "../../hooks/useFirstRows";
import { useResource } from "../../hooks/useResource";
import { bytes, hours } from "../../lib/format";
import { labelFor, MODE_LABELS, TASK_STATUS_LABELS } from "../../lib/labels";
import { languageLabel } from "../projects/choices";
import "./dashboard.css";

const HEADINGS: Record<Dashboard["view"], { title: string; lead: string }> = {
  client: { title: "Collection progress", lead: "Hours collected and approved for your projects." },
  worker: { title: "My work", lead: "Your own tasks and recordings only." },
  manager: { title: "Dashboard", lead: "Progress against targets and what needs attention." },
};

const percent = (part: number, whole: number) =>
  whole > 0 ? Math.min(100, Math.round((part / whole) * 100)) : 0;

/** What needs someone. A queue of tasks in one status opens the task list filtered to it. */
const QUEUES: { key: string; label: string; icon: IconName; status?: string }[] = [
  { key: "waiting_for_qc", label: "Waiting for audio QC", icon: "verified", status: "AUDIO_QC" },
  { key: "processing", label: "Being processed", icon: "waveform" },
  { key: "failed_processing", label: "Processing failed", icon: "failed" },
  { key: "interrupted", label: "Interrupted recordings", icon: "warning" },
  { key: "stale_uploads", label: "Stalled uploads", icon: "upload" },
  { key: "on_hold", label: "Tasks on hold", icon: "pause", status: "ON_HOLD" },
  // D-146: QC sent them back to their moderator for a new signed consent form.
  {
    key: "consent_forms_to_fix",
    label: "Consent forms to fix",
    icon: "fileUp",
    status: "CONSENT_FIX",
  },
];

/** The task list filtered to a status (and the chosen project). */
const tasksLink = (status: string, projectId: string | null) =>
  `/tasks?status=${status}${projectId ? `&project=${projectId}` : ""}`;

/** Face-to-face beside phone, and both together: one row per figure. */
function ByMode({ data }: { data: Dashboard }) {
  const modes = data.by_mode;
  const rows: { label: string; each: (m: Dashboard["by_mode"][number]) => string; all: string }[] =
    [
      { label: "Recordings", each: (m) => String(m.recordings), all: String(data.recordings) },
      { label: "Recorded", each: (m) => hours(m.recorded_hours), all: hours(data.recorded_hours) },
      {
        label: "Effective speech",
        each: (m) => hours(m.effective_hours),
        all: hours(data.effective_hours),
      },
      { label: "Approved", each: (m) => hours(m.approved_hours), all: hours(data.approved_hours) },
      {
        label: "Completed",
        each: (m) => hours(m.completed_hours),
        all: hours(data.completed_hours),
      },
    ];
  const target = (h: number) => (h > 0 ? `${h} h` : "Not set");
  if (data.view !== "worker")
    rows.push({
      label: "Daily target",
      each: (m) => target(m.target_hours_per_day),
      all: target(data.target_hours_per_day),
    });
  return (
    <DataTable label="By recording type" className="by-mode">
      <thead>
        <tr>
          <th scope="col">
            <span className="sr-only">Figure</span>
          </th>
          {modes.map((m) => (
            <th key={m.mode} scope="col" className="num">
              <span className="cell-icon">
                <Icon name={m.mode === "TELEPHONY" ? "phone" : "mic"} size={14} />
                {labelFor(MODE_LABELS, m.mode)}
              </span>
            </th>
          ))}
          <th scope="col" className="num">
            Total
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label}>
            <th scope="row">{r.label}</th>
            {modes.map((m) => (
              <td key={m.mode} className="num">
                {r.each(m)}
              </td>
            ))}
            <td className="num by-mode__total">{r.all}</td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}

/** Queues that need someone, with their counts; a queue of tasks opens the filtered task list. */
function Attention({
  queues,
  projectId,
}: {
  queues: Record<string, number>;
  projectId: string | null;
}) {
  return (
    <DataTable label="Needs attention" className="attention">
      <tbody>
        {QUEUES.map((q) => {
          const n = queues[q.key] ?? 0;
          return (
            <tr key={q.key} className={n > 0 ? "is-active" : undefined}>
              <th scope="row">
                <span className="cell-icon">
                  <Icon name={q.icon} size={16} />
                  {q.status ? <Link to={tasksLink(q.status, projectId)}>{q.label}</Link> : q.label}
                </span>
              </th>
              <td className="num">
                <span className="attention__n">{n}</span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </DataTable>
  );
}

const GOOD = "var(--icon-green)";
const WAIT = "var(--series-waiting)";
const BAD = "var(--icon-rose)";

/** Audio QC: the decisions, and the automatic check of the recordings still waiting. */
function AudioQc({ qc }: { qc: NonNullable<Dashboard["qc"]> }) {
  return (
    <>
      <SplitBar
        title="QC decisions"
        parts={[
          { key: "passed", label: "Passed", n: qc.passed, color: GOOD },
          { key: "rejected", label: "Rejected", n: qc.rejected, color: BAD },
          { key: "waiting", label: "Waiting", n: qc.waiting, color: WAIT },
        ]}
      />
      <SplitBar
        title="Automatic check of those waiting"
        parts={[
          { key: "pass", label: "All checks passed", n: qc.auto_pass, color: GOOD },
          { key: "review", label: "Listen and decide", n: qc.auto_review, color: WAIT },
          { key: "fail", label: "Failed a check", n: qc.auto_fail, color: BAD },
        ]}
      />
    </>
  );
}

/** What each moderator recorded: the first rows, and the rest on request. */
function Team({ team, className }: { team: NonNullable<Dashboard["team"]>; className: string }) {
  const { shown, more } = useFirstRows(team);
  const most = Math.max(0, ...team.map((t) => t.recorded_hours));
  return (
    <Panel className={className} icon="people" title="Moderator output">
      {team.length === 0 ? (
        <p className="muted">No finished recordings yet.</p>
      ) : (
        <DataTable label="Moderator output">
          <thead>
            <tr>
              <th scope="col">Moderator</th>
              <th scope="col" className="num">
                Recordings
              </th>
              <th scope="col" className="num team__hours">
                Hours
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((t) => (
              <tr key={t.name}>
                <th scope="row">
                  <span className="cell-person">
                    <Avatar name={t.name} />
                    {t.name}
                  </span>
                </th>
                <td className="num">{t.recordings}</td>
                <td className="num">
                  <CellBar value={t.recorded_hours} max={most}>
                    {hours(t.recorded_hours)}
                  </CellBar>
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
      {more}
    </Panel>
  );
}

function Body({ data }: { data: Dashboard }) {
  const daily = data.target_hours_per_day;
  const statuses = data.view === "client" ? [] : stageParts(data.tasks_by_status ?? {});
  const showCalls =
    data.calls !== null &&
    (data.calls.placed > 0 ||
      data.by_mode.some((m) => m.mode === "TELEPHONY" && m.target_hours_per_day > 0));
  // The third row holds what this view has: tasks by status, what needs attention, audio QC
  // (widest first: the status legend, then the queues, then the two QC bars).
  const third = [data.view !== "client", data.queues !== null, data.qc !== null].filter(
    Boolean,
  ).length;
  const spans = third === 3 ? ["g-5", "g-4", "g-3"] : third === 2 ? ["g-6", "g-6"] : [""];
  const [statusSpan, attentionSpan, qcSpan] = [
    data.view !== "client" ? spans.shift() : "",
    data.queues ? spans.shift() : "",
    data.qc ? spans.shift() : "",
  ];
  const notes = (
    <>
      Effective speech is the time someone speaks (silences left out). Completed counts each
      project&apos;s approved recordings as its rules say: effective speech or the full length;
      several projects add up their own.
      {data.effective_pending > 0
        ? ` ${data.effective_pending} recording${data.effective_pending === 1 ? " is" : "s are"} still being measured and count${data.effective_pending === 1 ? "s" : ""} no effective speech yet.`
        : ""}{" "}
      Days are counted in{" "}
      {data.timezone === "Asia/Kolkata"
        ? "India Standard Time"
        : `${data.timezone.replace("_", " ")} time`}
      .
    </>
  );
  return (
    <div className="dash">
      <KpiStrip label="Key figures">
        <Kpi
          icon="mic"
          label="Recorded"
          value={hours(data.recorded_hours)}
          note={`${data.recordings} recording${data.recordings === 1 ? "" : "s"}, ${hours(data.effective_hours)} effective speech`}
          spark={data.daily.map((d) => d.recorded_hours)}
        />
        <Kpi
          icon="verified"
          label="Approved"
          value={hours(data.approved_hours)}
          note={`${percent(data.approved_hours, data.recorded_hours)}% of recorded hours`}
          spark={data.daily.map((d) => d.approved_hours)}
        />
        {/* D-148: approved recordings counted as each project's rules say. */}
        <Kpi
          icon="ok"
          label="Completed"
          value={hours(data.completed_hours)}
          note={`approved, as each project counts it (effective speech ${hours(data.approved_effective_hours)})`}
          spark={data.daily.map((d) => d.completed_hours)}
        />
        <Kpi
          icon="clock"
          label="Today"
          value={hours(data.today_hours)}
          meter={
            data.view !== "worker" && daily > 0
              ? {
                  percent: percent(data.today_hours, daily),
                  label: "Today of the daily target",
                  text: `${percent(data.today_hours, daily)}%`,
                }
              : undefined
          }
          note={
            data.view === "worker"
              ? "recorded by you today"
              : daily > 0
                ? `of the ${daily} h daily target`
                : "No daily target set"
          }
        />
        <Kpi
          icon="tasks"
          label="Tasks approved"
          value={String(data.tasks_approved)}
          of={`/ ${data.tasks_total}`}
          meter={{
            percent: percent(data.tasks_approved, data.tasks_total),
            label: "Tasks approved of all tasks",
            text: `${percent(data.tasks_approved, data.tasks_total)}%`,
          }}
          note="tasks complete"
        />
      </KpiStrip>

      <div className="dash-grid">
        <div className="panel g-7">
          <DayChart
            title="Hours per day"
            height={196}
            days={data.daily}
            target={daily}
            emptyText="No finished recordings in this period yet."
            series={[
              { label: "Approved", className: "series--approved", value: (d) => d.approved_hours },
              {
                label: "Recorded, not yet approved",
                className: "series--waiting",
                value: (d) => Math.max(0, d.recorded_hours - d.approved_hours),
              },
            ]}
            columns={[
              { label: "Recorded", value: (d) => hours(d.recorded_hours) },
              { label: "Approved", value: (d) => hours(d.approved_hours) },
            ]}
          />
        </div>
        <Panel className="g-5" icon="mic" title="By recording type">
          <ByMode data={data} />
        </Panel>

        {data.view !== "client" ? (
          <Panel className={statusSpan} icon="tasks" title="Tasks by status">
            <Donut
              label="Tasks by status"
              parts={statuses}
              unit="tasks"
              emptyText="No tasks yet."
            />
          </Panel>
        ) : null}
        {data.queues ? (
          <Panel className={attentionSpan} icon="warning" title="Needs attention">
            <Attention queues={data.queues} projectId={data.project_id} />
          </Panel>
        ) : null}
        {data.qc ? (
          <Panel className={qcSpan} icon="verified" title="Audio QC">
            <AudioQc qc={data.qc} />
          </Panel>
        ) : null}

        {data.team ? <Team team={data.team} className="g-8" /> : null}
        {data.team || showCalls || data.storage_bytes !== null ? (
          <div className={data.team ? "dash-col g-4" : "dash-col"}>
            {data.calls && showCalls ? (
              <Panel icon="phone" title="Phone calls">
                <KeyTable
                  label="Phone calls"
                  rows={[
                    { label: "Placed", value: data.calls.placed },
                    { label: "Recorded", value: data.calls.recorded },
                    { label: "Could not be placed", value: data.calls.could_not_be_placed },
                    { label: "Waiting for a person", value: data.calls.needs_a_person },
                    { label: "Still open", value: data.calls.open },
                  ]}
                />
                <p className="muted">
                  More on the <Link to="/calls">Phone calls</Link> page.
                </p>
              </Panel>
            ) : null}
            {data.storage_bytes !== null ? (
              <Panel
                icon="archive"
                title="Storage used"
                action={<strong className="dash-storage">{bytes(data.storage_bytes)}</strong>}
              >
                <p className="muted">
                  Files kept in private storage, before retention deletes them.
                </p>
              </Panel>
            ) : null}
            {data.team ? (
              <Panel icon="info" title="How these are counted">
                <p className="muted">{notes}</p>
              </Panel>
            ) : null}
          </div>
        ) : null}
      </div>
      {data.team ? null : <p className="muted dash-foot">{notes}</p>}
    </div>
  );
}

const NO_FILTERS = {
  mode: "",
  language: "",
  dialect: "",
  district: "",
  status: "",
  staffId: "",
};

export function DashboardPage() {
  const [projectId, setProjectId] = useState("");
  const [period, setPeriod] = useState("30"); // 7, 30, 90 or "custom"
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [filters, setFilters] = useState(NO_FILTERS);
  const custom = period === "custom";
  const backwards = custom && from !== "" && to !== "" && from > to;
  const asked: DashboardFilters = {
    project_id: projectId || undefined,
    days: custom ? 30 : Number(period),
    mode: filters.mode || undefined,
    language: filters.language || undefined,
    dialect: filters.dialect || undefined,
    district: filters.district || undefined,
    status: filters.status || undefined,
    staff_id: filters.staffId || undefined,
    date_from: custom ? from || undefined : undefined,
    date_to: custom ? to || undefined : undefined,
  };
  const key = JSON.stringify(asked);
  const { state, reload } = useResource(
    () => (backwards ? Promise.resolve(null) : getDashboard(asked)),
    [key, backwards],
  );
  // What was loaded last stays on the page while the next answer is on its way, so the
  // filters do not lose their lists and the figures do not jump away.
  const [last, setLast] = useState<Dashboard | null>(null);
  const fresh = state.status === "loaded" ? state.data : null;
  if (fresh && fresh !== last) setLast(fresh);
  const data = fresh ?? last;
  const view = data?.view ?? "manager";
  const projects = data?.projects ?? [];
  const options = data?.options ?? {};
  const narrowed = Object.values(filters).some(Boolean) || custom;
  const set = (patch: Partial<typeof NO_FILTERS>) => setFilters((f) => ({ ...f, ...patch }));
  return (
    <section aria-labelledby="dash-title" className="stack stack--tight dash-page">
      <div className="page-header">
        <div className="page-header__text">
          <h1 id="dash-title">
            <IconTile name="chart" />
            {HEADINGS[view].title}
          </h1>
          <p className="page-header__lead">{HEADINGS[view].lead}</p>
        </div>
        <div className="toolbar">
          <Select
            label="Project"
            value={projectId}
            onChange={(e) => {
              setProjectId(e.target.value);
              // Another project has other people and languages.
              set({ language: "", dialect: "", district: "", staffId: "" });
            }}
            options={[
              { value: "", label: "All my projects" },
              ...projects.map((p) => ({ value: p.id, label: `${p.code} · ${p.name}` })),
            ]}
          />
          <Select
            label="Period"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            options={[
              { value: "7", label: "Last 7 days" },
              { value: "30", label: "Last 30 days" },
              { value: "90", label: "Last 90 days" },
              { value: "custom", label: "Choose dates (from – to)" },
            ]}
          />
        </div>
      </div>
      <div className="filters dash-filters" role="group" aria-label="Filters">
        {custom ? (
          <>
            <TextField
              label="From"
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
            <TextField
              label="To"
              type="date"
              value={to}
              {...(backwards ? { error: "Must not be before the first day" } : {})}
              onChange={(e) => setTo(e.target.value)}
            />
          </>
        ) : null}
        <Select
          label="Recording type"
          value={filters.mode}
          onChange={(e) => set({ mode: e.target.value })}
          options={[
            { value: "", label: "Every recording type" },
            ...Object.entries(MODE_LABELS).map(([value, label]) => ({ value, label })),
          ]}
        />
        <Select
          label="Language"
          value={filters.language}
          onChange={(e) => set({ language: e.target.value })}
          options={[
            { value: "", label: "Every language" },
            ...(options.languages ?? []).map((code) => ({
              value: code,
              label: languageLabel(code),
            })),
          ]}
        />
        {(options.dialects ?? []).length > 0 ? (
          <Select
            label="Dialect"
            value={filters.dialect}
            onChange={(e) => set({ dialect: e.target.value })}
            options={[
              { value: "", label: "Every dialect" },
              ...(options.dialects ?? []).map((d) => ({ value: d, label: d })),
            ]}
          />
        ) : null}
        {(options.districts ?? []).length > 0 ? (
          <Select
            label="District"
            value={filters.district}
            onChange={(e) => set({ district: e.target.value })}
            options={[
              { value: "", label: "Every district" },
              ...(options.districts ?? []).map((d) => ({ value: d, label: d })),
            ]}
          />
        ) : null}
        {view !== "client" ? (
          <Select
            label="Task status"
            value={filters.status}
            onChange={(e) => set({ status: e.target.value })}
            options={[
              { value: "", label: "Every status" },
              ...Object.entries(TASK_STATUS_LABELS).map(([value, label]) => ({ value, label })),
            ]}
          />
        ) : null}
        {options.staff ? (
          <Select
            label="Staff"
            value={filters.staffId}
            onChange={(e) => set({ staffId: e.target.value })}
            options={[
              { value: "", label: "Everyone" },
              ...options.staff.map((s) => ({ value: s.id, label: s.name })),
            ]}
          />
        ) : null}
        {narrowed ? (
          <Button
            variant="secondary"
            icon="filterX"
            onClick={() => {
              setFilters(NO_FILTERS);
              setPeriod("30");
              setFrom("");
              setTo("");
            }}
          >
            Clear filters
          </Button>
        ) : null}
      </div>
      {state.status === "loading" ? <LoadingState label="Loading dashboard" /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {data && state.status !== "failed" && !backwards ? <Body data={data} /> : null}
    </section>
  );
}

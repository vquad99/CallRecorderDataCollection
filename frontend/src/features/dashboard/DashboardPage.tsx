// Dashboard (DASH-001..006). One page, three views decided by the server: a client sees collection
// progress only; moderators and QC see their own work; managers also see what needs attention.
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { getDashboard, type Dashboard, type DashboardFilters } from "../../api/dashboard";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Bars, DayChart, Stat } from "../../components/charts/Charts";
import { Avatar, Icon, type IconName, IconTile } from "../../components/Icon";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useResource } from "../../hooks/useResource";
import { bytes, hours } from "../../lib/format";
import { labelFor, MODE_LABELS, TASK_STATUS_LABELS } from "../../lib/labels";
import { languageLabel } from "../projects/choices";
import "./dashboard.css";
import { DataTable } from "../../components/DataTable";

const HEADINGS: Record<Dashboard["view"], { title: string; lead: string }> = {
  client: { title: "Collection progress", lead: "Hours collected and approved for your projects." },
  worker: { title: "My work", lead: "Your own tasks and recordings only." },
  manager: { title: "Dashboard", lead: "Progress against targets and what needs attention." },
};

const percent = (part: number, whole: number) =>
  whole > 0 ? Math.min(100, Math.round((part / whole) * 100)) : 0;

const DONUT: Record<string, string> = {
  APPROVED: "var(--ok)",
  AUDIO_QC: "var(--warn)",
  ADMIN_REVIEW: "var(--info)",
  RECORDED: "var(--series-approved)",
  IN_PROGRESS: "var(--primary)",
  ASSIGNED: "var(--violet)",
  DRAFT: "var(--border-strong)",
  REJECTED: "var(--danger)",
  ON_HOLD: "var(--amber)",
  CANCELLED: "var(--muted)",
};

function Donut({ parts, total }: { parts: [string, number][]; total: number }) {
  const r = 42;
  const c = 2 * Math.PI * r;
  const starts = parts.map((_, i) =>
    parts.slice(0, i).reduce((sum, [, n]) => sum + (n / total) * c, 0),
  );
  return (
    <svg className="donut" viewBox="0 0 110 110" aria-hidden="true">
      <circle cx="55" cy="55" r={r} className="donut__track" />
      {parts.map(([status, n], i) => (
        <circle
          key={status}
          cx="55"
          cy="55"
          r={r}
          fill="none"
          strokeWidth="14"
          stroke={DONUT[status] ?? "var(--muted)"}
          strokeDasharray={`${Math.max(0, (n / total) * c - 2)} ${c}`}
          strokeDashoffset={-(starts[i] ?? 0)}
          transform="rotate(-90 55 55)"
        />
      ))}
      <text x="55" y="53" textAnchor="middle" className="donut__total">
        {total}
      </text>
      <text x="55" y="68" textAnchor="middle" className="donut__label">
        tasks
      </text>
    </svg>
  );
}

/** What needs someone. A queue of tasks in one status opens the task list filtered to it. */
const QUEUES: { key: string; label: string; icon: IconName; status?: string }[] = [
  { key: "waiting_for_qc", label: "Waiting for audio QC", icon: "verified", status: "AUDIO_QC" },
  { key: "processing", label: "Being processed", icon: "waveform" },
  { key: "failed_processing", label: "Processing failed", icon: "failed" },
  { key: "interrupted", label: "Interrupted recordings", icon: "warning" },
  { key: "stale_uploads", label: "Stalled uploads", icon: "upload" },
  { key: "on_hold", label: "Tasks on hold", icon: "stop", status: "ON_HOLD" },
];

/** The task list filtered to a status (and the chosen project). */
const tasksLink = (status: string, projectId: string | null) =>
  `/tasks?status=${status}${projectId ? `&project=${projectId}` : ""}`;

function Body({ data }: { data: Dashboard }) {
  const todayPct = percent(data.today_hours, data.target_hours_per_day);
  const statuses = useMemo(
    () =>
      Object.entries(data.tasks_by_status ?? {})
        .filter(([, n]) => n > 0)
        .sort((a, b) => b[1] - a[1]),
    [data.tasks_by_status],
  );
  return (
    <>
      <div className="stats">
        <Stat
          icon="mic"
          tone="blue"
          label="Recorded"
          value={hours(data.recorded_hours)}
          note={`${data.recordings} recording${data.recordings === 1 ? "" : "s"}`}
          spark={data.daily.map((d) => d.recorded_hours)}
        />
        <Stat
          icon="verified"
          tone="green"
          label="Approved"
          value={hours(data.approved_hours)}
          note={`${percent(data.approved_hours, data.recorded_hours)}% of recorded hours`}
          spark={data.daily.map((d) => d.approved_hours)}
        />
        <Stat
          icon="target"
          tone="amber"
          label="Today"
          value={hours(data.today_hours)}
          note={
            data.view === "worker"
              ? "recorded by you today"
              : data.target_hours_per_day > 0
                ? `of the ${data.target_hours_per_day} h daily target`
                : "No daily target set"
          }
          ring={data.target_hours_per_day > 0 ? todayPct : undefined}
        />
        <Stat
          icon="tasks"
          tone="violet"
          label="Tasks approved"
          value={`${data.tasks_approved} / ${data.tasks_total}`}
          note="tasks complete"
          ring={percent(data.tasks_approved, data.tasks_total)}
        />
      </div>

      <div className="card">
        <DayChart
          title="Hours per day"
          days={data.daily}
          target={data.target_hours_per_day}
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

      <div className="split">
        {data.by_mode.map((m) => (
          <div key={m.mode} className="card mode">
            <h2 className="with-icon">
              <IconTile
                name={m.mode === "TELEPHONY" ? "phone" : "mic"}
                tone={m.mode === "TELEPHONY" ? "violet" : "teal"}
                size={28}
              />
              {labelFor(MODE_LABELS, m.mode)}
            </h2>
            <dl className="checks">
              <div className="checks__row">
                <dt>Recorded</dt>
                <dd>{hours(m.recorded_hours)}</dd>
              </div>
              <div className="checks__row">
                <dt>Approved</dt>
                <dd>{hours(m.approved_hours)}</dd>
              </div>
              {data.view === "worker" ? null : (
                <div className="checks__row">
                  <dt>Daily target</dt>
                  <dd>{m.target_hours_per_day > 0 ? `${m.target_hours_per_day} h` : "Not set"}</dd>
                </div>
              )}
            </dl>
          </div>
        ))}
      </div>

      {data.view !== "client" ? (
        <div className="split">
          <section className="card" aria-labelledby="by-status">
            <h2 id="by-status">Tasks by status</h2>
            {statuses.length === 0 ? (
              <p className="muted">No tasks yet.</p>
            ) : (
              <div className="status-split">
                <Donut parts={statuses} total={statuses.reduce((n, [, v]) => n + v, 0)} />
                <Bars
                  empty="No tasks yet."
                  rows={statuses.map(([s, n]) => ({
                    key: s,
                    label: <StatusBadge status={s} label={labelFor(TASK_STATUS_LABELS, s)} />,
                    n,
                    color: DONUT[s] ?? "var(--muted)",
                  }))}
                />
              </div>
            )}
          </section>
          {data.qc ? (
            <section className="card" aria-labelledby="qc-title">
              <h2 id="qc-title">Audio QC</h2>
              <dl className="checks">
                <div className="checks__row">
                  <dt>Passed</dt>
                  <dd>{data.qc.passed}</dd>
                </div>
                <div className="checks__row">
                  <dt>Rejected</dt>
                  <dd>{data.qc.rejected}</dd>
                </div>
                <div className="checks__row">
                  <dt>Waiting</dt>
                  <dd>{data.qc.waiting}</dd>
                </div>
              </dl>
              <h3>Automatic check of those waiting</h3>
              <dl className="checks">
                <div className="checks__row">
                  <dt>All checks passed</dt>
                  <dd>{data.qc.auto_pass}</dd>
                </div>
                <div className="checks__row">
                  <dt>Listen and decide</dt>
                  <dd>{data.qc.auto_review}</dd>
                </div>
                <div className="checks__row">
                  <dt>Failed a check</dt>
                  <dd>{data.qc.auto_fail}</dd>
                </div>
              </dl>
            </section>
          ) : null}
        </div>
      ) : null}

      {data.queues ? (
        <section aria-labelledby="attention" className="stack stack--tight">
          <h2 id="attention">Needs attention</h2>
          <div className="queues">
            {QUEUES.map((q) => {
              const n = data.queues?.[q.key] ?? 0;
              const inner = (
                <>
                  <Icon name={q.icon} size={18} />
                  <span className="queue__label">{q.label}</span>
                  <span className="queue__value">{n}</span>
                </>
              );
              const className = n > 0 ? "queue queue--active" : "queue";
              return q.status ? (
                <Link key={q.key} className={className} to={tasksLink(q.status, data.project_id)}>
                  {inner}
                </Link>
              ) : (
                <div key={q.key} className={className}>
                  {inner}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {data.calls &&
      (data.calls.placed > 0 ||
        data.by_mode.some((m) => m.mode === "TELEPHONY" && m.target_hours_per_day > 0)) ? (
        <section className="card" aria-labelledby="calls-title">
          <h2 id="calls-title" className="with-icon">
            <IconTile name="phone" tone="violet" size={28} />
            Phone calls
          </h2>
          <dl className="checks">
            <div className="checks__row">
              <dt>Placed</dt>
              <dd>{data.calls.placed}</dd>
            </div>
            <div className="checks__row">
              <dt>Recorded</dt>
              <dd>{data.calls.recorded}</dd>
            </div>
            <div className="checks__row">
              <dt>Could not be placed</dt>
              <dd>{data.calls.could_not_be_placed}</dd>
            </div>
            <div className="checks__row">
              <dt>Waiting for a person</dt>
              <dd>{data.calls.needs_a_person}</dd>
            </div>
            <div className="checks__row">
              <dt>Still open</dt>
              <dd>{data.calls.open}</dd>
            </div>
          </dl>
          <p className="muted">
            More on the <Link to="/calls">Phone calls</Link> page.
          </p>
        </section>
      ) : null}

      {data.team ? (
        <div className="split split--wide">
          <section className="card" aria-labelledby="team-title">
            <h2 id="team-title">Moderator output</h2>
            {data.team.length === 0 ? (
              <p className="muted">No finished recordings yet.</p>
            ) : (
              <DataTable>
                <thead>
                  <tr>
                    <th scope="col">Moderator</th>
                    <th scope="col">Recordings</th>
                    <th scope="col">Hours</th>
                  </tr>
                </thead>
                <tbody>
                  {data.team.map((t) => (
                    <tr key={t.name}>
                      <td>
                        <span className="cell-person">
                          <Avatar name={t.name} />
                          {t.name}
                        </span>
                      </td>
                      <td>{t.recordings}</td>
                      <td>{hours(t.recorded_hours)}</td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            )}
          </section>
          <section className="card" aria-labelledby="storage-title">
            <h2 id="storage-title">Storage used</h2>
            <p className="stat__value">{bytes(data.storage_bytes ?? 0)}</p>
            <p className="muted">Files kept in private storage, before retention deletes them.</p>
          </section>
        </div>
      ) : null}
      <p className="muted">
        Days are counted in{" "}
        {data.timezone === "Asia/Kolkata"
          ? "India Standard Time"
          : `${data.timezone.replace("_", " ")} time`}
        .
      </p>
    </>
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
    <section aria-labelledby="dash-title" className="stack">
      <div className="page-header">
        <div className="page-header__text">
          <h1 id="dash-title">
            <IconTile name="chart" tone="blue" />
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
      <div className="filters" role="group" aria-label="Filters">
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

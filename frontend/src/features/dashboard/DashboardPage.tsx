// Dashboard (DASH-001..006). One page, three views decided by the server: a client sees collection
// progress only; moderators and QC see their own work; managers also see what needs attention.
import { useId, useMemo, useState } from "react";

import { TASK_STATUS_LABELS, type TaskStatus } from "../../api/work";
import { getDashboard, type Dashboard, type DayTotals } from "../../api/dashboard";
import { Select } from "../../components/form/Select";
import { Avatar, Icon, type IconName, IconTile } from "../../components/Icon";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useResource } from "../../hooks/useResource";
import "./dashboard.css";

const HEADINGS: Record<Dashboard["view"], { title: string; lead: string }> = {
  client: { title: "Collection progress", lead: "Hours collected and approved for your projects." },
  worker: { title: "My work", lead: "Your own tasks and recordings only." },
  manager: { title: "Dashboard", lead: "Progress against targets and what needs attention." },
};

const hours = (h: number) =>
  h >= 10 ? `${h.toFixed(0)} h` : h >= 1 ? `${h.toFixed(1)} h` : `${Math.round(h * 60)} min`;
const percent = (part: number, whole: number) =>
  whole > 0 ? Math.min(100, Math.round((part / whole) * 100)) : 0;
const dayLabel = (iso: string, opts: Intl.DateTimeFormatOptions) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, opts);

function bytes(n: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

type Tone = "blue" | "teal" | "violet" | "amber" | "rose" | "green" | "slate";

function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(...values, 0.0001);
  const step = 100 / Math.max(1, values.length - 1);
  const pts = values.map((v, i) => `${(i * step).toFixed(1)},${(28 - (v / max) * 24).toFixed(1)}`);
  return (
    <svg className="spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
      <polygon points={`0,30 ${pts.join(" ")} 100,30`} />
      <polyline points={pts.join(" ")} />
    </svg>
  );
}

function Ring({ value }: { value: number }) {
  const r = 20;
  const c = 2 * Math.PI * r;
  return (
    <svg className="ring" viewBox="0 0 52 52" aria-hidden="true">
      <circle cx="26" cy="26" r={r} className="ring__track" />
      <circle
        cx="26"
        cy="26"
        r={r}
        className="ring__value"
        strokeDasharray={`${(value / 100) * c} ${c}`}
        transform="rotate(-90 26 26)"
      />
      <text x="26" y="30" textAnchor="middle">
        {value}%
      </text>
    </svg>
  );
}

function Stat({
  icon,
  tone,
  label,
  value,
  note,
  ring,
  spark,
}: {
  icon: IconName;
  tone: Tone;
  label: string;
  value: string;
  note?: string;
  ring?: number | undefined;
  spark?: number[];
}) {
  return (
    <div className="stat">
      <div className="stat__head">
        <IconTile name={icon} tone={tone} size={34} />
        <span className="stat__label">{label}</span>
      </div>
      <div className="stat__body">
        <div>
          <p className="stat__value">{value}</p>
          {note ? <p className="stat__note">{note}</p> : null}
        </div>
        {ring !== undefined ? <Ring value={ring} /> : null}
        {spark ? <Sparkline values={spark} /> : null}
      </div>
    </div>
  );
}

const DONUT: Record<string, string> = {
  APPROVED: "var(--ok)",
  AUDIO_QC: "var(--warn)",
  RECORDED: "var(--series-approved)",
  IN_PROGRESS: "var(--primary)",
  ASSIGNED: "var(--violet)",
  DRAFT: "var(--border-strong)",
  RETURNED: "var(--series-waiting)",
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

/** Daily hours as stacked bars (approved + awaiting approval) with the daily target as a line. */
function DailyChart({ days, target }: { days: DayTotals[]; target: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const titleId = useId();
  const max = Math.max(target, ...days.map((d) => d.recorded_hours));
  const empty = days.every((d) => d.recorded_hours === 0);
  const top = max > 0 ? max * 1.15 : 1;
  const W = 1000;
  const H = 260;
  const PAD_L = 40;
  const PAD_B = 26;
  const plotW = W - PAD_L;
  const plotH = H - PAD_B - 8;
  const slot = plotW / days.length;
  const barW = Math.max(3, Math.min(18, slot - 4));
  const y = (v: number) => 8 + plotH - (v / top) * plotH;
  const ticks = [0, top / 2, top].map((t) => Math.round(t * 10) / 10);
  const labelEvery = days.length > 31 ? 14 : days.length > 14 ? 7 : 1;
  const shown = hover === null ? null : days[hover];

  return (
    <figure className="chart" aria-labelledby={titleId}>
      <figcaption className="chart__head">
        <h2 id={titleId}>Hours per day</h2>
        <ul className="legend">
          <li>
            <span className="legend__swatch legend__swatch--approved" aria-hidden="true" />
            Approved
          </li>
          <li>
            <span className="legend__swatch legend__swatch--waiting" aria-hidden="true" />
            Recorded, not yet approved
          </li>
          {target > 0 ? (
            <li>
              <span className="legend__line" aria-hidden="true" />
              Daily target
            </li>
          ) : null}
        </ul>
      </figcaption>
      <div className="chart__plot">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Hours per day, see the table below">
          {ticks.map((t) => (
            <g key={t}>
              <line className="chart__grid" x1={PAD_L} x2={W} y1={y(t)} y2={y(t)} />
              <text className="chart__tick" x={PAD_L - 8} y={y(t) + 4} textAnchor="end">
                {t}
              </text>
            </g>
          ))}
          {days.map((d, i) => {
            const x = PAD_L + i * slot + (slot - barW) / 2;
            const approved = d.approved_hours;
            const waiting = Math.max(0, d.recorded_hours - d.approved_hours);
            const yA = y(approved);
            const yW = y(approved + waiting);
            return (
              <g
                key={d.day}
                className={hover === i ? "chart__day is-hover" : "chart__day"}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              >
                <rect
                  className="chart__hit"
                  x={PAD_L + i * slot}
                  y={8}
                  width={slot}
                  height={plotH}
                />
                {approved > 0 ? (
                  <rect
                    className="chart__bar chart__bar--approved"
                    x={x}
                    y={yA}
                    width={barW}
                    height={Math.max(1, y(0) - yA)}
                    rx={Math.min(4, barW / 2)}
                  />
                ) : null}
                {waiting > 0 ? (
                  <rect
                    className="chart__bar chart__bar--waiting"
                    x={x}
                    y={yW}
                    width={barW}
                    height={Math.max(1, yA - yW - (approved > 0 ? 2 : 0))}
                    rx={Math.min(4, barW / 2)}
                  />
                ) : null}
                {(days.length - 1 - i) % labelEvery === 0 ? (
                  <text className="chart__tick" x={x + barW / 2} y={H - 6} textAnchor="middle">
                    {dayLabel(d.day, { day: "numeric", month: "short" })}
                  </text>
                ) : null}
              </g>
            );
          })}
          <line className="chart__axis" x1={PAD_L} x2={W} y1={y(0)} y2={y(0)} />
          {target > 0 ? (
            <line className="chart__target" x1={PAD_L} x2={W} y1={y(target)} y2={y(target)} />
          ) : null}
        </svg>
        {empty ? (
          <p className="chart__empty">
            <span>No finished recordings in this period yet.</span>
          </p>
        ) : null}
        {shown ? (
          <div
            className="chart__tooltip"
            style={{ left: `${((PAD_L + (hover ?? 0) * slot + slot / 2) / W) * 100}%` }}
            aria-hidden="true"
          >
            <strong>
              {dayLabel(shown.day, { weekday: "short", day: "numeric", month: "short" })}
            </strong>
            <span>Recorded {hours(shown.recorded_hours)}</span>
            <span>Approved {hours(shown.approved_hours)}</span>
          </div>
        ) : null}
      </div>
      <details className="chart__table">
        <summary>Show as a table</summary>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">Recorded</th>
                <th scope="col">Approved</th>
              </tr>
            </thead>
            <tbody>
              {[...days].reverse().map((d) => (
                <tr key={d.day}>
                  <td>{dayLabel(d.day, { weekday: "short", day: "numeric", month: "short" })}</td>
                  <td>{hours(d.recorded_hours)}</td>
                  <td>{hours(d.approved_hours)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

const QUEUES: { key: string; label: string; icon: IconName }[] = [
  { key: "waiting_for_qc", label: "Waiting for audio QC", icon: "verified" },
  { key: "processing", label: "Being processed", icon: "waveform" },
  { key: "failed_processing", label: "Processing failed", icon: "failed" },
  { key: "interrupted", label: "Interrupted recordings", icon: "warning" },
  { key: "stale_uploads", label: "Stalled uploads", icon: "upload" },
  { key: "on_hold", label: "Tasks on hold", icon: "stop" },
];

function Body({ data }: { data: Dashboard }) {
  const todayPct = percent(data.today_hours, data.target_hours_per_day);
  const statuses = useMemo(
    () =>
      Object.entries(data.tasks_by_status ?? {})
        .filter(([, n]) => n > 0)
        .sort((a, b) => b[1] - a[1]),
    [data.tasks_by_status],
  );
  const maxStatus = Math.max(1, ...statuses.map(([, n]) => n));
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
        <DailyChart days={data.daily} target={data.target_hours_per_day} />
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
              {m.mode === "TELEPHONY" ? "Telephony" : "Face-to-face"}
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
                <ul className="bars">
                  {statuses.map(([s, n]) => (
                    <li key={s}>
                      <StatusBadge status={s} label={TASK_STATUS_LABELS[s as TaskStatus] ?? s} />
                      <span className="bars__track" aria-hidden="true">
                        <span
                          style={{
                            width: `${(n / maxStatus) * 100}%`,
                            background: DONUT[s] ?? "var(--muted)",
                          }}
                        />
                      </span>
                      <span className="bars__value">{n}</span>
                    </li>
                  ))}
                </ul>
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
                  <dt>Returned</dt>
                  <dd>{data.qc.returned}</dd>
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
              return (
                <div key={q.key} className={n > 0 ? "queue queue--active" : "queue"}>
                  <Icon name={q.icon} size={18} />
                  <span className="queue__label">{q.label}</span>
                  <span className="queue__value">{n}</span>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {data.team ? (
        <div className="split split--wide">
          <section className="card" aria-labelledby="team-title">
            <h2 id="team-title">Moderator output</h2>
            {data.team.length === 0 ? (
              <p className="muted">No finished recordings yet.</p>
            ) : (
              <table className="table">
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
              </table>
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

export function DashboardPage() {
  const [projectId, setProjectId] = useState("");
  const [days, setDays] = useState(30);
  const { state, reload } = useResource(
    () => getDashboard({ project_id: projectId || undefined, days }),
    [projectId, days],
  );
  const view = state.status === "loaded" ? state.data.view : "manager";
  const projects = state.status === "loaded" ? state.data.projects : [];
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
            onChange={(e) => setProjectId(e.target.value)}
            options={[
              { value: "", label: "All my projects" },
              ...projects.map((p) => ({ value: p.id, label: `${p.code} · ${p.name}` })),
            ]}
          />
          <Select
            label="Period"
            value={String(days)}
            onChange={(e) => setDays(Number(e.target.value))}
            options={[
              { value: "7", label: "Last 7 days" },
              { value: "30", label: "Last 30 days" },
              { value: "90", label: "Last 90 days" },
            ]}
          />
        </div>
      </div>
      {state.status === "loading" ? <LoadingState label="Loading dashboard" /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? <Body data={state.data} /> : null}
    </section>
  );
}

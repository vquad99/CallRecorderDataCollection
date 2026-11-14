// Phone calls (D-101, D-102, D-103): how calls are going, from the platform's own call records,
// plus TxContact's own count of calls per hour, and every call with a link to its task.
import { useId, useState } from "react";
import { Link } from "react-router";

import type { ApiError } from "../../api/client";
import { listProjects } from "../../api/projects";
import * as tel from "../../api/telephony";
import { TASK_STATUS_LABELS, type TaskStatus } from "../../api/work";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { Icon, IconTile, type IconName } from "../../components/Icon";
import { ErrorNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAuth } from "../../auth/AuthContext";
import { toApiError, useResource } from "../../hooks/useResource";
import "../dashboard/dashboard.css";
import { CallBadge, span, words } from "./callUi";

const dayLabel = (iso: string, opts: Intl.DateTimeFormatOptions) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, opts);
const minutes = (m: number | null) => span(m === null ? null : m * 60);
const pct = (part: number, whole: number) => (whole > 0 ? Math.round((part / whole) * 100) : 0);

function Figure({
  icon,
  label,
  value,
  note,
}: {
  icon: IconName;
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="stat">
      <div className="stat__head">
        <IconTile name={icon} tone="blue" size={34} />
        <span className="stat__label">{label}</span>
      </div>
      <div className="stat__body">
        <div>
          <p className="stat__value">{value}</p>
          {note ? <p className="stat__note">{note}</p> : null}
        </div>
      </div>
    </div>
  );
}

const SERIES = [
  { key: "recorded", label: "Recorded", className: "calls-series--recorded" },
  { key: "open", label: "Still open", className: "calls-series--open" },
  { key: "failed", label: "Failed or cancelled", className: "calls-series--failed" },
] as const;

/** Calls per day, stacked by how they ended, with a hover tooltip and a table view. */
function CallsPerDay({ days }: { days: tel.CallDay[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const titleId = useId();
  const max = Math.max(1, ...days.map((d) => d.calls));
  const top = Math.ceil(max * 1.15);
  const W = 1000;
  const H = 240;
  const PAD_L = 36;
  const PAD_B = 26;
  const plotW = W - PAD_L;
  const plotH = H - PAD_B - 8;
  const slot = plotW / days.length;
  const barW = Math.max(3, Math.min(18, slot - 4));
  const y = (v: number) => 8 + plotH - (v / top) * plotH;
  const ticks = Array.from(new Set([0, Math.round(top / 2), top]));
  const labelEvery = days.length > 31 ? 14 : days.length > 14 ? 7 : 1;
  const shown = hover === null ? null : days[hover];
  const empty = days.every((d) => d.calls === 0);
  return (
    <figure className="chart" aria-labelledby={titleId}>
      <figcaption className="chart__head">
        <h2 id={titleId}>Calls per day</h2>
        <ul className="legend">
          {SERIES.map((s) => (
            <li key={s.key}>
              <span className={`legend__swatch ${s.className}`} aria-hidden="true" />
              {s.label}
            </li>
          ))}
        </ul>
      </figcaption>
      <div className="chart__plot calls-plot">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Calls per day, see the table below">
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
            let base = 0;
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
                {SERIES.map((s) => {
                  const n = d[s.key];
                  if (n === 0) return null;
                  const y1 = y(base);
                  const y2 = y(base + n);
                  const gap = base > 0 ? 2 : 0;
                  base += n;
                  return (
                    <rect
                      key={s.key}
                      className={s.className}
                      x={x}
                      y={y2}
                      width={barW}
                      height={Math.max(1, y1 - y2 - gap)}
                      rx={Math.min(4, barW / 2)}
                    />
                  );
                })}
                {(days.length - 1 - i) % labelEvery === 0 ? (
                  <text className="chart__tick" x={x + barW / 2} y={H - 6} textAnchor="middle">
                    {dayLabel(d.day, { day: "numeric", month: "short" })}
                  </text>
                ) : null}
              </g>
            );
          })}
          <line className="chart__axis" x1={PAD_L} x2={W} y1={y(0)} y2={y(0)} />
        </svg>
        {empty ? (
          <p className="chart__empty">
            <span>No calls in this period yet.</span>
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
            <span>{shown.calls} call(s)</span>
            <span>
              Recorded {shown.recorded} ({minutes(shown.recorded_minutes)})
            </span>
            <span>Still open {shown.open}</span>
            <span>Failed or cancelled {shown.failed}</span>
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
                <th scope="col">Calls</th>
                <th scope="col">Recorded</th>
                <th scope="col">Recorded audio</th>
                <th scope="col">Still open</th>
                <th scope="col">Failed or cancelled</th>
              </tr>
            </thead>
            <tbody>
              {[...days].reverse().map((d) => (
                <tr key={d.day}>
                  <td>{dayLabel(d.day, { weekday: "short", day: "numeric", month: "short" })}</td>
                  <td>{d.calls}</td>
                  <td>{d.recorded}</td>
                  <td>{minutes(d.recorded_minutes)}</td>
                  <td>{d.open}</td>
                  <td>{d.failed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

/** Calls started in each hour of the day (one series: the title names it). */
function CallsByHour({ hours, title }: { hours: number[]; title: string }) {
  const max = Math.max(1, ...hours);
  const busiest = hours.indexOf(Math.max(...hours));
  return (
    <section className="card" aria-label={title}>
      <h2>{title}</h2>
      {hours.every((n) => n === 0) ? (
        <p className="muted">No calls in this period yet.</p>
      ) : (
        <>
          <ol className="hours" aria-hidden="true">
            {hours.map((n, h) => (
              <li key={h} title={`${String(h).padStart(2, "0")}:00 · ${n} call(s)`}>
                <span className="hours__bar" style={{ height: `${(n / max) * 100}%` }} />
                <span className="hours__tick">{h % 3 === 0 ? String(h).padStart(2, "0") : ""}</span>
              </li>
            ))}
          </ol>
          <p className="muted">
            Busiest hour: {String(busiest).padStart(2, "0")}:00 ({hours[busiest]} call(s)).
          </p>
          <details className="chart__table">
            <summary>Show as a table</summary>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Hour</th>
                  <th scope="col">Calls</th>
                </tr>
              </thead>
              <tbody>
                {hours.map((n, h) =>
                  n > 0 ? (
                    <tr key={h}>
                      <td>{String(h).padStart(2, "0")}:00</td>
                      <td>{n}</td>
                    </tr>
                  ) : null,
                )}
              </tbody>
            </table>
          </details>
        </>
      )}
    </section>
  );
}

/** Rows of "label, thin bar, number": reasons, problems, statuses, the funnel. */
function Bars({
  rows,
  max,
  empty,
}: {
  rows: { key: string; label: string; n: number; note?: string }[];
  max?: number;
  empty: string;
}) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.n));
  if (rows.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ul className="bars calls-bars">
      {rows.map((r) => (
        <li key={r.key}>
          <span>{r.label}</span>
          <span className="bars__track" aria-hidden="true">
            <span style={{ width: `${top > 0 ? (r.n / top) * 100 : 0}%` }} />
          </span>
          <span className="bars__value">
            {r.n}
            {r.note ? <span className="muted calls-bars__note"> {r.note}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Counts({
  title,
  counts,
  labels,
  empty = "None in this period.",
}: {
  title: string;
  counts: Record<string, number>;
  labels: Record<string, string>;
  empty?: string;
}) {
  return (
    <section className="card" aria-label={title}>
      <h2>{title}</h2>
      <Bars
        rows={Object.entries(counts).map(([k, n]) => ({ key: k, label: labels[k] ?? words(k), n }))}
        empty={empty}
      />
    </section>
  );
}

const FUNNEL: { key: keyof tel.CallFunnel; label: string }[] = [
  { key: "dialled", label: "Calls started" },
  { key: "accepted", label: "Accepted by TxContact" },
  { key: "closed", label: "Closed by the moderator" },
  { key: "recorded", label: "Recording stored" },
  { key: "sent_to_qc", label: "Sent to QC (tasks)" },
  { key: "approved", label: "Approved (tasks)" },
];

/** From dial to approval: where calls are lost on the way. */
function Funnel({ funnel }: { funnel: tel.CallFunnel }) {
  return (
    <section className="card" aria-labelledby="funnel-title">
      <h2 id="funnel-title">From call to approval</h2>
      <Bars
        max={funnel.dialled}
        rows={FUNNEL.map((f) => ({
          key: f.key,
          label: f.label,
          n: funnel[f.key],
          note: funnel.dialled > 0 ? `${pct(funnel[f.key], funnel.dialled)}%` : "",
        }))}
        empty="No calls in this period yet."
      />
    </section>
  );
}

/** TxContact's own hour-of-day counts: its answer's shape is not described, so a map or list of
 * numbers is drawn and anything else is shown as received. */
function ProviderTraffic({ days }: { days: number }) {
  const { state, reload } = useResource(() => tel.providerTraffic(days), [days]);
  if (state.status === "loading") return <LoadingState label="Asking TxContact" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  const t = state.data;
  const title = "TxContact: calls per hour (its own count)";
  if (!t.available) {
    return (
      <section className="card" aria-label={title}>
        <h2>{title}</h2>
        <p className="muted">Not available: {t.message}.</p>
      </section>
    );
  }
  const hours = Array.from({ length: 24 }, () => 0);
  let drawable = false;
  const source = t.data;
  if (Array.isArray(source) && source.every((v) => typeof v === "number")) {
    source.slice(0, 24).forEach((v, i) => (hours[i] = v as number));
    drawable = true;
  } else if (source && typeof source === "object") {
    for (const [k, v] of Object.entries(source as Record<string, unknown>)) {
      const h = Number.parseInt(k, 10);
      if (Number.isInteger(h) && h >= 0 && h < 24 && typeof v === "number") {
        hours[h] = v;
        drawable = true;
      }
    }
  }
  return drawable ? (
    <CallsByHour hours={hours} title={title} />
  ) : (
    <section className="card" aria-label={title}>
      <h2>{title}</h2>
      <pre className="calls-raw">{JSON.stringify(source, null, 2)}</pre>
    </section>
  );
}

function CallList({ projectId }: { projectId: string }) {
  const [page, setPage] = useState(1);
  const [state, setState] = useState("");
  const list = useResource(
    () =>
      tel.listAllCalls({
        project_id: projectId || undefined,
        state: state || undefined,
        page,
        page_size: 25,
      }),
    [projectId, state, page],
  );
  return (
    <section className="card" aria-labelledby="all-calls">
      <div className="calls-list__head">
        <h2 id="all-calls">All calls</h2>
        <Select
          label="Show"
          value={state}
          onChange={(e) => {
            setState(e.target.value);
            setPage(1);
          }}
          options={[
            { value: "", label: "Every call" },
            { value: "NEEDS_PERSON", label: "Needs a person" },
            ...Object.entries(tel.CALL_STATE_LABELS).map(([value, label]) => ({ value, label })),
          ]}
        />
      </div>
      {list.state.status === "loading" ? <LoadingState /> : null}
      {list.state.status === "failed" ? (
        <ErrorState error={list.state.error} onRetry={list.reload} />
      ) : null}
      {list.state.status === "loaded" && list.state.data.items.length === 0 ? (
        <p className="muted">No calls.</p>
      ) : null}
      {list.state.status === "loaded" && list.state.data.items.length > 0 ? (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Started</th>
                  <th scope="col">Task</th>
                  <th scope="col">Moderator</th>
                  <th scope="col">State</th>
                  <th scope="col">Call</th>
                  <th scope="col">Recording</th>
                  <th scope="col">Why</th>
                </tr>
              </thead>
              <tbody>
                {list.state.data.items.map((c) => (
                  <tr key={c.id}>
                    <td>{new Date(c.dialled_at).toLocaleString()}</td>
                    <td>
                      <Link to={`/tasks/${c.task_id}`}>{c.task_code}</Link>{" "}
                      <span className="muted">{c.project_code}</span>
                    </td>
                    <td>
                      {c.moderator_name} <span className="muted">seat {c.agent_id}</span>
                    </td>
                    <td>
                      <CallBadge state={c.state} stale={c.stale} />
                    </td>
                    <td>
                      {c.closed_at && c.state !== "DIAL_FAILED"
                        ? span(
                            (new Date(c.closed_at).getTime() - new Date(c.dialled_at).getTime()) /
                              1000,
                          )
                        : "-"}
                    </td>
                    <td>{span(c.recording_seconds)}</td>
                    <td>
                      {c.cancel_reason
                        ? tel.CANCEL_REASONS[c.cancel_reason]
                        : c.failure_code && c.state !== "RECORDED"
                          ? (tel.FAILURE_LABELS[c.failure_code] ?? words(c.failure_code))
                          : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={list.state.data.page}
            pageSize={list.state.data.page_size}
            total={list.state.data.total}
            onPage={setPage}
          />
        </>
      ) : null}
    </section>
  );
}

function Body({ data, allProjects }: { data: tel.CallAnalytics; allProjects: boolean }) {
  const target = data.target_minutes_per_day;
  const closed = data.checklist.closed_calls ?? 0;
  return (
    <>
      {data.truncated ? (
        <p role="status" className="muted">
          This period has more calls than one page of figures can count: the newest 50,000 are
          shown. Choose a project or a shorter period.
        </p>
      ) : null}
      <div className="stats">
        <Figure
          icon="phone"
          label="Calls"
          value={String(data.calls)}
          note={`${data.in_call} on a call now`}
        />
        <Figure
          icon="verified"
          label="Recorded"
          value={String(data.recorded)}
          note={data.success_pct === null ? "No calls yet" : `${data.success_pct}% of calls`}
        />
        <Figure
          icon="failed"
          label="Failed or cancelled"
          value={String(data.dial_failed + data.cancelled)}
          note={`${data.dial_failed} not placed · ${data.cancelled} cancelled`}
        />
        <Figure
          icon="warning"
          label="Needs a person"
          value={String(data.needs_person)}
          note={`${data.stale_calls} left open · ${data.waiting_for_recording} being fetched`}
        />
        <Figure
          icon="clock"
          label="Average call"
          value={minutes(data.avg_call_minutes)}
          note={data.calls_per_task === null ? "" : `${data.calls_per_task} call(s) for each task`}
        />
        <Figure
          icon="waveform"
          label="Recorded audio"
          value={minutes(data.recorded_minutes)}
          note={`Arrives ${minutes(data.avg_fetch_minutes)} after closing, on average`}
        />
        <Figure
          icon="target"
          label="Today"
          value={minutes(data.today_recorded_minutes)}
          note={
            target === null
              ? "Recorded today"
              : target > 0
                ? `${pct(data.today_recorded_minutes, target)}% of the daily target (${minutes(target)})`
                : "No daily target set"
          }
        />
        <Figure
          icon="tasks"
          label="Tasks not called yet"
          value={String(data.tasks_not_called)}
          note={`${data.tasks_called_again} task(s) called more than once`}
        />
      </div>
      <section className="card">
        <CallsPerDay days={data.by_day} />
      </section>
      <div className="split">
        <Funnel funnel={data.funnel} />
        <section className="card" aria-labelledby="phone-tasks">
          <h2 id="phone-tasks">Phone tasks by status</h2>
          <Bars
            rows={Object.entries(data.tasks_by_status).map(([status, n]) => ({
              key: status,
              label: TASK_STATUS_LABELS[status as TaskStatus] ?? words(status),
              n,
            }))}
            empty="No phone tasks yet."
          />
        </section>
      </div>
      <div className="split">
        <CallsByHour hours={data.by_hour} title="Calls by hour of the day" />
        <section className="card" aria-labelledby="by-moderator">
          <h2 id="by-moderator">By moderator</h2>
          {data.by_moderator.length === 0 ? (
            <p className="muted">No calls in this period yet.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Moderator</th>
                    <th scope="col">Calls</th>
                    <th scope="col">Recorded</th>
                    <th scope="col">Failed or cancelled</th>
                    <th scope="col">Recorded audio</th>
                    <th scope="col">Average call</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_moderator.map((m) => (
                    <tr key={m.moderator_id}>
                      <td>{m.name}</td>
                      <td>{m.calls}</td>
                      <td>{m.recorded}</td>
                      <td>{m.failed}</td>
                      <td>{minutes(m.recorded_minutes)}</td>
                      <td>{minutes(m.avg_call_minutes)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
      {allProjects && data.by_project.length > 1 ? (
        <section className="card" aria-labelledby="by-project">
          <h2 id="by-project">By project</h2>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Project</th>
                  <th scope="col">Calls</th>
                  <th scope="col">Recorded</th>
                  <th scope="col">Failed or cancelled</th>
                  <th scope="col">Recorded audio</th>
                </tr>
              </thead>
              <tbody>
                {data.by_project.map((p) => (
                  <tr key={p.project_id}>
                    <td>
                      <Link to={`/projects/${p.project_id}`}>{p.code}</Link>{" "}
                      <span className="muted">{p.name}</span>
                    </td>
                    <td>{p.calls}</td>
                    <td>{p.recorded}</td>
                    <td>{p.failed}</td>
                    <td>{minutes(p.recorded_minutes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
      <div className="split">
        <Counts
          title="Automatic audio check of call recordings"
          counts={data.automatic_checks}
          labels={tel.AUTOMATIC_CHECK_LABELS}
          empty="No call recording checked in this period."
        />
        <Counts
          title="QC decisions on call recordings"
          counts={data.qc_decisions}
          labels={tel.QC_DECISION_LABELS}
          empty="No QC decision in this period."
        />
      </div>
      <div className="split">
        <Counts
          title="Why calls were cancelled"
          counts={data.cancel_reasons}
          labels={tel.CANCEL_REASONS}
        />
        <Counts
          title="Problems getting the recording"
          counts={data.problems}
          labels={tel.FAILURE_LABELS}
        />
      </div>
      <section className="card" aria-labelledby="checklist-title">
        <h2 id="checklist-title">Call checklist on closed calls</h2>
        <Bars
          max={closed}
          rows={
            closed > 0
              ? tel.CHECKLIST.map((c) => ({
                  key: c.item,
                  label: c.label,
                  n: data.checklist[c.item] ?? 0,
                  note: `of ${closed}`,
                }))
              : []
          }
          empty="No closed call in this period."
        />
      </section>
    </>
  );
}

export function CallsPage() {
  const { can } = useAuth();
  const [projectId, setProjectId] = useState("");
  const [days, setDays] = useState(30);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<ApiError | null>(null);
  const projects = useResource(() => listProjects({ page_size: 100 }), []);
  const { state, reload } = useResource(
    () => tel.callAnalytics({ project_id: projectId || undefined, days }),
    [projectId, days],
  );
  return (
    <section aria-labelledby="calls-title" className="stack">
      <div className="page-header">
        <div className="page-header__text">
          <h1 id="calls-title">
            <IconTile name="phone" tone="blue" />
            Phone calls
          </h1>
          <p className="page-header__lead">
            Calls made through TxContact: how many, how they ended, and every call.
          </p>
        </div>
        <div className="toolbar">
          <Select
            label="Project"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            options={[
              { value: "", label: "All my projects" },
              ...(projects.state.status === "loaded" ? projects.state.data.items : []).map((p) => ({
                value: p.id,
                label: `${p.code} · ${p.name}`,
              })),
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
          <Button
            variant="secondary"
            busy={saving}
            onClick={() => {
              setSaving(true);
              setSaveError(null);
              tel
                .downloadCallsCsv({ project_id: projectId || undefined, days })
                .catch((err: unknown) => setSaveError(toApiError(err)))
                .finally(() => setSaving(false));
            }}
          >
            <Icon name="upload" size={15} />
            Download calls (CSV)
          </Button>
        </div>
      </div>
      <ErrorNotice error={saveError} />
      {state.status === "loading" ? <LoadingState label="Loading call figures" /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? <Body data={state.data} allProjects={projectId === ""} /> : null}
      {can("tasks.assign") ? <ProviderTraffic days={days} /> : null}
      {/* A new list for each project: it starts again at its first page. */}
      <CallList key={projectId} projectId={projectId} />
    </section>
  );
}

// Phone calls (D-101, D-102, D-103): how calls are going, from the platform's own call records,
// plus TxContact's own count of calls per hour; and, on its own tab, every call with a link to its
// task. Moderators see a plain list of their own calls (D-104).
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { listProjects } from "../../api/projects";
import * as tel from "../../api/telephony";
import { useAuth } from "../../auth/AuthContext";
import { Bars, DayChart, Stat } from "../../components/charts/Charts";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { Icon, IconTile } from "../../components/Icon";
import { ErrorNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { duration, when } from "../../lib/format";
import { labelFor, TASK_STATUS_LABELS } from "../../lib/labels";
import { CallBadge } from "./callUi";

const minutes = (m: number | null) => duration(m === null ? null : m * 60);
const pct = (part: number, whole: number) => (whole > 0 ? Math.round((part / whole) * 100) : 0);
/** Rows a table shows before "Show all". */
const FIRST_ROWS = 10;

/** A table's first rows, and a button for the rest. */
function useFirstRows<T>(rows: T[]) {
  const [all, setAll] = useState(false);
  const more =
    rows.length > FIRST_ROWS ? (
      <span>
        <Button variant="secondary" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all (${rows.length})`}
        </Button>
      </span>
    ) : null;
  return { shown: all ? rows : rows.slice(0, FIRST_ROWS), more };
}

/** Calls started in each hour of the day (one series: the title names it). */
function CallsByHour({ hours, title }: { hours: number[]; title: string }) {
  const max = Math.max(1, ...hours);
  const busiest = hours.indexOf(Math.max(...hours));
  const hour = (h: number) => `${String(h).padStart(2, "0")}:00`;
  return (
    <section className="card" aria-label={title}>
      <h2>{title}</h2>
      {hours.every((n) => n === 0) ? (
        <p className="muted">No calls in this period yet.</p>
      ) : (
        <>
          <ol className="hours" aria-hidden="true">
            {hours.map((n, h) => (
              <li key={h} title={`${hour(h)} · ${n} call(s)`}>
                <span className="hours__bar" style={{ height: `${(n / max) * 100}%` }} />
                <span className="hours__tick">{h % 3 === 0 ? String(h).padStart(2, "0") : ""}</span>
              </li>
            ))}
          </ol>
          <p className="muted">
            Busiest hour: {hour(busiest)} ({hours[busiest]} call(s)).
          </p>
          <details className="chart__table">
            <summary>Show as a table</summary>
            <DataTable label={title}>
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
                      <td>{hour(h)}</td>
                      <td>{n}</td>
                    </tr>
                  ) : null,
                )}
              </tbody>
            </DataTable>
          </details>
        </>
      )}
    </section>
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
        wide
        rows={Object.entries(counts).map(([k, n]) => ({ key: k, label: labelFor(labels, k), n }))}
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
        wide
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
 * numbers is drawn; anything else is only described, with the answer for the Super Admin. */
function ProviderTraffic({ days }: { days: number }) {
  const superAdmin = Boolean(useAuth().user?.roles.includes("SUPER_ADMIN"));
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
      <p className="muted">TxContact answered, but not with counts per hour that can be drawn.</p>
      {superAdmin ? (
        <details className="tech-log">
          <summary>Technical details</summary>
          <pre className="calls-raw">{JSON.stringify(source, null, 2)}</pre>
        </details>
      ) : null}
    </section>
  );
}

function CallList({ projectId, title }: { projectId: string; title: string }) {
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
        <h2 id="all-calls">{title}</h2>
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
          <DataTable>
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
                  <td>{when(c.dialled_at)}</td>
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
                      ? duration((Date.parse(c.closed_at) - Date.parse(c.dialled_at)) / 1000)
                      : "-"}
                  </td>
                  <td>{duration(c.recording_seconds)}</td>
                  <td>
                    {c.cancel_reason
                      ? tel.CANCEL_REASONS[c.cancel_reason]
                      : c.failure_code && c.state !== "RECORDED"
                        ? labelFor(tel.FAILURE_LABELS, c.failure_code)
                        : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
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

function ByModerator({ rows }: { rows: tel.ModeratorCalls[] }) {
  const { shown, more } = useFirstRows(rows);
  return (
    <section className="card stack stack--tight" aria-labelledby="by-moderator">
      <h2 id="by-moderator">By moderator</h2>
      {rows.length === 0 ? (
        <p className="muted">No calls in this period yet.</p>
      ) : (
        <>
          <DataTable>
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
              {shown.map((m) => (
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
          </DataTable>
          {more}
        </>
      )}
    </section>
  );
}

function ByProject({ rows }: { rows: tel.ProjectCalls[] }) {
  const { shown, more } = useFirstRows(rows);
  return (
    <section className="card stack stack--tight" aria-labelledby="by-project">
      <h2 id="by-project">By project</h2>
      <DataTable>
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
          {shown.map((p) => (
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
      </DataTable>
      {more}
    </section>
  );
}

function Figures({ data, allProjects }: { data: tel.CallAnalytics; allProjects: boolean }) {
  const target = data.target_minutes_per_day;
  return (
    <>
      {data.truncated ? (
        <p role="status" className="muted">
          This period has more calls than one page of figures can count: the newest 50,000 are
          shown. Choose a project or a shorter period.
        </p>
      ) : null}
      <div className="stats">
        <Stat
          icon="phone"
          label="Calls"
          value={String(data.calls)}
          note={`${data.in_call} on a call now`}
        />
        <Stat
          icon="verified"
          label="Recorded"
          value={String(data.recorded)}
          note={data.success_pct === null ? "No calls yet" : `${data.success_pct}% of calls`}
        />
        <Stat
          icon="failed"
          label="Failed or cancelled"
          value={String(data.dial_failed + data.cancelled)}
          note={`${data.dial_failed} not placed · ${data.cancelled} cancelled`}
        />
        <Stat
          icon="warning"
          label="Needs a person"
          value={String(data.needs_person)}
          note={`${data.stale_calls} left open · ${data.waiting_for_recording} being fetched`}
        />
        <Stat
          icon="clock"
          label="Average call"
          value={minutes(data.avg_call_minutes)}
          note={data.calls_per_task === null ? "" : `${data.calls_per_task} call(s) for each task`}
        />
        <Stat
          icon="waveform"
          label="Recorded audio"
          value={minutes(data.recorded_minutes)}
          note={`Arrives ${minutes(data.avg_fetch_minutes)} after closing, on average`}
        />
        <Stat
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
        <Stat
          icon="tasks"
          label="Tasks not called yet"
          value={String(data.tasks_not_called)}
          note={`${data.tasks_called_again} task(s) called more than once`}
        />
      </div>
      <section className="card">
        <DayChart
          title="Calls per day"
          wholeNumbers
          days={data.by_day}
          emptyText="No calls in this period yet."
          series={[
            { label: "Recorded", className: "series--recorded", value: (d) => d.recorded },
            { label: "Still open", className: "series--open", value: (d) => d.open },
            { label: "Failed or cancelled", className: "series--failed", value: (d) => d.failed },
          ]}
          columns={[
            { label: "Calls", value: (d) => d.calls },
            { label: "Recorded", value: (d) => d.recorded },
            { label: "Recorded audio", value: (d) => minutes(d.recorded_minutes) },
            { label: "Still open", value: (d) => d.open },
            { label: "Failed or cancelled", value: (d) => d.failed },
          ]}
        />
      </section>
      <div className="split">
        <Funnel funnel={data.funnel} />
        <section className="card" aria-labelledby="phone-tasks">
          <h2 id="phone-tasks">Phone tasks by status</h2>
          <Bars
            wide
            rows={Object.entries(data.tasks_by_status).map(([status, n]) => ({
              key: status,
              label: labelFor(TASK_STATUS_LABELS, status),
              n,
            }))}
            empty="No phone tasks yet."
          />
        </section>
      </div>
      <div className="split">
        <CallsByHour hours={data.by_hour} title="Calls by hour of the day" />
        <ByModerator rows={data.by_moderator} />
      </div>
      {allProjects && data.by_project.length > 1 ? <ByProject rows={data.by_project} /> : null}
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
    </>
  );
}

/** A project filter shared by both views. */
function ProjectSelect({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const projects = useResource(() => listProjects({ page_size: 100 }), []);
  return (
    <Select
      label="Project"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      options={[
        { value: "", label: "All my projects" },
        ...(projects.state.status === "loaded" ? projects.state.data.items : []).map((p) => ({
          value: p.id,
          label: `${p.code} · ${p.name}`,
        })),
      ]}
    />
  );
}

function Header({ title, lead, children }: { title: string; lead: string; children: ReactNode }) {
  return (
    <div className="page-header">
      <div className="page-header__text">
        <h1 id="calls-title">
          <IconTile name="phone" tone="blue" />
          {title}
        </h1>
        <p className="page-header__lead">{lead}</p>
      </div>
      <div className="toolbar">{children}</div>
    </div>
  );
}

/** For people who make calls but do not assign tasks (moderators): their own calls, as a list
 * with links to the tasks. The figures are for the people who run the project (D-104). */
function MyCalls() {
  const [projectId, setProjectId] = useState("");
  return (
    <section aria-labelledby="calls-title" className="stack">
      <Header
        title="My phone calls"
        lead="The calls you made, newest first. Open a task to continue with its call."
      >
        <ProjectSelect value={projectId} onChange={setProjectId} />
      </Header>
      <CallList key={projectId} projectId={projectId} title="My calls" />
    </section>
  );
}

export function CallsPage() {
  const { can } = useAuth();
  return can("tasks.assign") ? <CallFigures /> : <MyCalls />;
}

const VIEWS = [
  { id: "figures", label: "Figures" },
  { id: "calls", label: "All calls" },
] as const;

function CallFigures() {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "calls" ? "calls" : "figures";
  const [projectId, setProjectId] = useState("");
  const [days, setDays] = useState(30);
  const download = useAction();
  const { state, reload } = useResource(
    () =>
      view === "figures"
        ? tel.callAnalytics({ project_id: projectId || undefined, days })
        : Promise.resolve(null),
    [projectId, days, view],
  );
  return (
    <section aria-labelledby="calls-title" className="stack">
      <Header title="Phone calls" lead="Calls made through TxContact: how many and how they ended.">
        <ProjectSelect value={projectId} onChange={setProjectId} />
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
          busy={download.busy !== null}
          onClick={() =>
            void download.run(() =>
              tel.downloadCallsCsv({ project_id: projectId || undefined, days }),
            )
          }
        >
          <Icon name="download" size={15} />
          Download calls (CSV)
        </Button>
      </Header>
      <ErrorNotice error={download.error} />
      <div className="tabs" role="tablist" aria-label="Phone call views">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            role="tab"
            id={`calls-tab-${v.id}`}
            aria-selected={view === v.id}
            aria-controls="calls-panel"
            className={view === v.id ? "tabs__link active" : "tabs__link"}
            onClick={() => setParams(v.id === "calls" ? { view: "calls" } : {}, { replace: true })}
          >
            {v.label}
          </button>
        ))}
      </div>
      <div id="calls-panel" role="tabpanel" aria-labelledby={`calls-tab-${view}`} className="stack">
        {view === "calls" ? (
          // A new list for each project: it starts again at its first page.
          <CallList key={projectId} projectId={projectId} title="All calls" />
        ) : (
          <>
            {state.status === "loading" ? <LoadingState label="Loading call figures" /> : null}
            {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
            {state.status === "loaded" && state.data ? (
              <Figures data={state.data} allProjects={projectId === ""} />
            ) : null}
            <ProviderTraffic days={days} />
          </>
        )}
      </div>
    </section>
  );
}

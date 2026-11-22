// Phone calls (D-101, D-102, D-103): how calls are going, from the platform's own call records,
// plus TxContact's own count of calls per hour; and, on its own tab, every call with a link to its
// task. Moderators see a plain list of their own calls (D-104). The figures are one dashboard
// (D-151): key figures in one strip, then charts and tables in a grid.
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { listProjects } from "../../api/projects";
import * as tel from "../../api/telephony";
import { useAuth } from "../../auth/AuthContext";
import {
  CellBar,
  DayChart,
  Donut,
  Kpi,
  KpiStrip,
  MatrixTable,
  Panel,
  type MatrixSection,
} from "../../components/charts/Charts";
import { stageParts } from "../../components/charts/stages";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { IconTile } from "../../components/Icon";
import { ErrorNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useFirstRows } from "../../hooks/useFirstRows";
import { useResource } from "../../hooks/useResource";
import { duration, when } from "../../lib/format";
import { labelFor } from "../../lib/labels";
import { CallBadge } from "./callUi";

const minutes = (m: number | null) => duration(m === null ? null : m * 60);
const pct = (part: number, whole: number) => (whole > 0 ? Math.round((part / whole) * 100) : 0);

/** Calls started in each hour of the day (one series: the title names it). */
function CallsByHour({
  hours,
  title,
  className,
}: {
  hours: number[];
  title: string;
  className?: string | undefined;
}) {
  const max = Math.max(1, ...hours);
  const busiest = hours.indexOf(Math.max(...hours));
  const hour = (h: number) => `${String(h).padStart(2, "0")}:00`;
  return (
    <Panel className={className} icon="clock" title={title}>
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
    </Panel>
  );
}

/** The counted lists as two tables side by side: a section per kind, a row per reason with its
 * count and a light bar for its share of the section's largest. */
function Reasons({ data }: { data: tel.CallAnalytics }) {
  type Row = { key: string; label: string; n: number; max: number };
  const section = (
    key: string,
    title: string,
    counts: Record<string, number>,
    labels: Record<string, string>,
    empty: string,
  ): MatrixSection<Row> => {
    const entries = Object.entries(counts);
    const max = Math.max(0, ...entries.map(([, n]) => n));
    return {
      key,
      title,
      empty,
      rows: entries.map(([k, n]) => ({ key: k, label: labelFor(labels, k), n, max })),
    };
  };
  const table = (label: string, sections: MatrixSection<Row>[]) => (
    <MatrixTable<Row>
      label={label}
      head="Reason"
      columns={[
        {
          key: "n",
          label: "Count",
          num: true,
          cell: (r) => (
            <CellBar value={r.n} max={r.max}>
              {r.n}
            </CellBar>
          ),
        },
      ]}
      sections={sections}
      rowKey={(r) => r.key}
      rowLabel={(r) => r.label}
    />
  );
  return (
    <div className="reasons">
      {table("Checks and QC decisions", [
        section(
          "checks",
          "Automatic audio check of call recordings",
          data.automatic_checks,
          tel.AUTOMATIC_CHECK_LABELS,
          "No call recording checked in this period.",
        ),
        section(
          "qc",
          "QC decisions on call recordings",
          data.qc_decisions,
          tel.QC_DECISION_LABELS,
          "No QC decision in this period.",
        ),
      ])}
      {table("Cancelled calls and recording problems", [
        section(
          "cancelled",
          "Why calls were cancelled",
          data.cancel_reasons,
          tel.CANCEL_REASONS,
          "None in this period.",
        ),
        section(
          "problems",
          "Problems getting the recording",
          data.problems,
          tel.FAILURE_LABELS,
          "None in this period.",
        ),
      ])}
    </div>
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
function Funnel({ funnel, className }: { funnel: tel.CallFunnel; className: string }) {
  return (
    <Panel className={className} icon="target" title="From call to approval">
      <DataTable label="From call to approval" className="funnel">
        <thead>
          <tr>
            <th scope="col">Step</th>
            <th scope="col" className="num">
              Calls
            </th>
            <th scope="col" className="num">
              Of started
            </th>
          </tr>
        </thead>
        <tbody>
          {FUNNEL.map((f) => (
            <tr key={f.key}>
              <th scope="row">{f.label}</th>
              <td className="num">
                <CellBar value={funnel[f.key]} max={funnel.dialled}>
                  {funnel[f.key]}
                </CellBar>
              </td>
              <td className="num">
                {funnel.dialled > 0 ? `${pct(funnel[f.key], funnel.dialled)}%` : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </Panel>
  );
}

/** TxContact's own hour-of-day counts: its answer's shape is not described, so a map or list of
 * numbers is drawn; anything else is only described, with the answer for the Super Admin. */
function ProviderTraffic({ days, className }: { days: number; className?: string | undefined }) {
  const superAdmin = Boolean(useAuth().user?.roles.includes("SUPER_ADMIN"));
  const { state, reload } = useResource(() => tel.providerTraffic(days), [days]);
  const title = "TxContact: calls per hour (its own count)";
  if (state.status === "loading")
    return (
      <Panel className={className} icon="clock" title={title}>
        <LoadingState label="Asking TxContact" />
      </Panel>
    );
  if (state.status === "failed")
    return (
      <Panel className={className} icon="clock" title={title}>
        <ErrorState error={state.error} onRetry={reload} />
      </Panel>
    );
  const t = state.data;
  if (!t.available) {
    return (
      <Panel className={className} icon="clock" title={title}>
        <p className="muted">Not available: {t.message}.</p>
      </Panel>
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
    <CallsByHour hours={hours} title={title} className={className} />
  ) : (
    <Panel className={className} icon="clock" title={title}>
      <p className="muted">TxContact answered, but not with counts per hour that can be drawn.</p>
      {superAdmin ? (
        <details className="tech-log">
          <summary>Technical details</summary>
          <pre className="calls-raw">{JSON.stringify(source, null, 2)}</pre>
        </details>
      ) : null}
    </Panel>
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

function ByModerator({ rows, className }: { rows: tel.ModeratorCalls[]; className: string }) {
  const { shown, more } = useFirstRows(rows);
  const most = Math.max(0, ...rows.map((m) => m.calls));
  return (
    <Panel className={className} icon="people" title="By moderator">
      {rows.length === 0 ? (
        <p className="muted">No calls in this period yet.</p>
      ) : (
        <>
          <DataTable label="By moderator">
            <thead>
              <tr>
                <th scope="col">Moderator</th>
                <th scope="col" className="num">
                  Calls
                </th>
                <th scope="col" className="num">
                  Recorded
                </th>
                <th scope="col" className="num">
                  Failed or cancelled
                </th>
                <th scope="col" className="num">
                  Recorded audio
                </th>
                <th scope="col" className="num">
                  Average call
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((m) => (
                <tr key={m.moderator_id}>
                  <th scope="row">{m.name}</th>
                  <td className="num">
                    <CellBar value={m.calls} max={most}>
                      {m.calls}
                    </CellBar>
                  </td>
                  <td className="num">{m.recorded}</td>
                  <td className="num">{m.failed}</td>
                  <td className="num">{minutes(m.recorded_minutes)}</td>
                  <td className="num">{minutes(m.avg_call_minutes)}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
          {more}
        </>
      )}
    </Panel>
  );
}

function ByProject({ rows, className }: { rows: tel.ProjectCalls[]; className: string }) {
  const { shown, more } = useFirstRows(rows);
  const most = Math.max(0, ...rows.map((p) => p.calls));
  return (
    <Panel className={className} icon="projects" title="By project">
      <DataTable label="By project">
        <thead>
          <tr>
            <th scope="col">Project</th>
            <th scope="col" className="num">
              Calls
            </th>
            <th scope="col" className="num">
              Recorded
            </th>
            <th scope="col" className="num">
              Failed or cancelled
            </th>
            <th scope="col" className="num">
              Recorded audio
            </th>
          </tr>
        </thead>
        <tbody>
          {shown.map((p) => (
            <tr key={p.project_id}>
              <th scope="row">
                <Link to={`/projects/${p.project_id}`}>{p.code}</Link>{" "}
                <span className="muted">{p.name}</span>
              </th>
              <td className="num">
                <CellBar value={p.calls} max={most}>
                  {p.calls}
                </CellBar>
              </td>
              <td className="num">{p.recorded}</td>
              <td className="num">{p.failed}</td>
              <td className="num">{minutes(p.recorded_minutes)}</td>
            </tr>
          ))}
        </tbody>
      </DataTable>
      {more}
    </Panel>
  );
}

function Figures({
  data,
  allProjects,
  traffic,
}: {
  data: tel.CallAnalytics;
  allProjects: boolean;
  /** TxContact's own count, loaded on its own. */
  traffic: ReactNode;
}) {
  const target = data.target_minutes_per_day;
  const byProject = allProjects && data.by_project.length > 1;
  return (
    <div className="dash">
      {data.truncated ? (
        <p role="status" className="muted">
          This period has more calls than one page of figures can count: the newest 50,000 are
          shown. Choose a project or a shorter period.
        </p>
      ) : null}
      <KpiStrip label="Call figures">
        <Kpi
          icon="phone"
          label="Calls"
          value={String(data.calls)}
          note={`${data.in_call} on a call now`}
        />
        <Kpi
          icon="verified"
          label="Recorded"
          value={String(data.recorded)}
          note={data.success_pct === null ? "No calls yet" : `${data.success_pct}% of calls`}
        />
        <Kpi
          icon="failed"
          label="Failed or cancelled"
          value={String(data.dial_failed + data.cancelled)}
          note={`${data.dial_failed} not placed · ${data.cancelled} cancelled`}
        />
        <Kpi
          icon="warning"
          label="Needs a person"
          value={String(data.needs_person)}
          note={`${data.stale_calls} left open · ${data.waiting_for_recording} being fetched`}
        />
        <Kpi
          icon="clock"
          label="Average call"
          value={minutes(data.avg_call_minutes)}
          note={data.calls_per_task === null ? "" : `${data.calls_per_task} call(s) for each task`}
        />
        <Kpi
          icon="waveform"
          label="Recorded audio"
          value={minutes(data.recorded_minutes)}
          note={`Arrives ${minutes(data.avg_fetch_minutes)} after closing, on average`}
        />
        <Kpi
          icon="target"
          label="Today"
          value={minutes(data.today_recorded_minutes)}
          meter={
            target !== null && target > 0
              ? {
                  percent: pct(data.today_recorded_minutes, target),
                  label: "Recorded today of the daily target",
                  text: `${pct(data.today_recorded_minutes, target)}%`,
                }
              : undefined
          }
          note={
            target === null
              ? "Recorded today"
              : target > 0
                ? `${pct(data.today_recorded_minutes, target)}% of the daily target (${minutes(target)})`
                : "No daily target set"
          }
        />
        <Kpi
          icon="tasks"
          label="Tasks not called yet"
          value={String(data.tasks_not_called)}
          note={`${data.tasks_called_again} task(s) called more than once`}
        />
      </KpiStrip>
      <div className="dash-grid">
        <div className="panel g-8">
          <DayChart
            title="Calls per day"
            wholeNumbers
            height={196}
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
        </div>
        <Funnel className="g-4" funnel={data.funnel} />
        <ByModerator className="g-8" rows={data.by_moderator} />
        <Panel className="g-4" icon="tasks" title="Phone tasks by status">
          <Donut
            label="Phone tasks by status"
            unit="tasks"
            emptyText="No phone tasks yet."
            parts={stageParts(data.tasks_by_status)}
          />
        </Panel>
        <Panel className="g-8" icon="warning" title="Checks, decisions and reasons">
          <Reasons data={data} />
        </Panel>
        <div className="dash-col g-4">
          <CallsByHour hours={data.by_hour} title="Calls by hour of the day" />
          {traffic}
        </div>
        {byProject ? <ByProject className="" rows={data.by_project} /> : null}
      </div>
    </div>
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
          <IconTile name="phone" />
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
    <section aria-labelledby="calls-title" className="stack stack--tight calls-page">
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
          icon="fileCsv"
          busy={download.busy !== null}
          onClick={() =>
            void download.run(() =>
              tel.downloadCallsCsv({ project_id: projectId || undefined, days }),
            )
          }
        >
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
              <Figures
                data={state.data}
                allProjects={projectId === ""}
                traffic={<ProviderTraffic days={days} />}
              />
            ) : (
              <ProviderTraffic days={days} />
            )}
          </>
        )}
      </div>
    </section>
  );
}

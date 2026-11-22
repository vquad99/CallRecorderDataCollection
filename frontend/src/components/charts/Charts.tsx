// Figures and charts shared by the dashboard, the Phone calls page and a project's Progress tab
// (D-151, D-154): a plain section with its heading, the key figures as one line, bars per day, a
// whole in parts as a table with a bar in each row, a bar to a target for table cells, a light bar
// behind a number, and tables with row sections. SVG and CSS only. Every chart has its numbers as
// text too: the day chart has "Show as a table", and the bars in table cells repeat a number in
// the same row.
import {
  Children,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";

import { dayLabel } from "../../lib/format";
import { DataTable } from "../DataTable";
import { IconTile, type IconName, type Tone } from "../Icon";
import "./charts.css";

/** A section of a dashboard (D-154): its heading, an optional link or note on its right, and its
 * table or chart under it; no box. `icon` is accepted from older callers and not drawn. */
export function Panel({
  title,
  action,
  className,
  children,
}: {
  title: string;
  icon?: IconName;
  action?: ReactNode;
  className?: string | undefined;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section className={className ? `panel ${className}` : "panel"} aria-labelledby={id}>
      <div className="panel__head">
        <h2 id={id}>{title}</h2>
        {action ? <div className="panel__action">{action}</div> : null}
      </div>
      {children}
    </section>
  );
}

/** The key figures as one line (D-154): each a label over its value, with an optional "of" and a
 * short note under it, thin lines between them; two columns on a phone. */
export function FigureLine({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="figs" role="group" aria-label={label}>
      <dl className="figline">{children}</dl>
    </div>
  );
}

export function Figure({
  label,
  value,
  of,
  note,
}: {
  label: string;
  value: string;
  /** What the value is out of, written smaller after it: "/ 600", "of 12 h". */
  of?: string | undefined;
  note?: ReactNode;
}) {
  return (
    <div className="figline__item">
      <dt>{label}</dt>
      <dd className="figline__value">
        {value}
        {of ? <span className="figline__of"> {of}</span> : null}
      </dd>
      {note ? <dd className="figline__note">{note}</dd> : null}
    </div>
  );
}

/** A share as a short bar and its percent, for a table cell. */
export function ShareBar({ percent }: { percent: number }) {
  const width = Math.max(0, Math.min(100, percent));
  return (
    <span className="sharebar">
      <span className="sharebar__track" aria-hidden="true">
        <span style={{ width: `${width}%` }} />
      </span>
      <span className="sharebar__n">{Math.round(percent)}%</span>
    </span>
  );
}

/** A whole in parts as a plain table (D-154): a row per part with its count and its share as a
 * bar, a second line under a part's name for what it is made of, and the total at the foot. */
export function ShareTable({
  label,
  head,
  countHead,
  parts,
  emptyText,
}: {
  label: string;
  /** The first column's heading: "Stage". */
  head: string;
  /** The count column's heading: "Tasks". */
  countHead: string;
  parts: DonutPart[];
  emptyText: string;
}) {
  const total = parts.reduce((n, p) => n + p.n, 0);
  if (total === 0) return <p className="muted">{emptyText}</p>;
  return (
    <DataTable label={label} className="share-table">
      <thead>
        <tr>
          <th scope="col">{head}</th>
          <th scope="col" className="num">
            {countHead}
          </th>
          <th scope="col" className="num">
            Share
          </th>
        </tr>
      </thead>
      <tbody>
        {parts.map((p) => (
          <tr key={p.key}>
            <th scope="row">
              {p.label}
              {p.detail ? <span className="share-table__detail">{p.detail}</span> : null}
            </th>
            <td className="num">{p.n}</td>
            <td className="num">
              <ShareBar percent={(p.n / total) * 100} />
            </td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row">Total</th>
          <td className="num">{total}</td>
          <td />
        </tr>
      </tfoot>
    </DataTable>
  );
}

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

/** A thin bar for a share of a target; its percent is written beside it by the caller. */
export function Meter({ percent, label }: { percent: number; label: string }) {
  const value = Math.max(0, Math.min(100, percent));
  return (
    <span
      className="meter"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value)}
    >
      <span style={{ width: `${value}%` }} />
    </span>
  );
}

/** A strip of key figures: one row on a wide screen, two rows (then two columns) when narrower. */
export function KpiStrip({ label, children }: { label: string; children: ReactNode }) {
  const n = Children.toArray(children).length;
  const style = { "--n": n, "--n-mid": n > 4 ? Math.ceil(n / 2) : n } as CSSProperties;
  return (
    <div className="kpis" role="group" aria-label={label}>
      <div className="kpis__grid" style={style}>
        {children}
      </div>
    </div>
  );
}

/** One key figure: label, value (with "of" a target), a bar to the target, a note, a trend. */
export function Kpi({
  icon,
  tone,
  label,
  value,
  of,
  meter,
  note,
  spark,
}: {
  icon: IconName;
  tone?: Tone;
  label: string;
  value: string;
  /** What the value is out of, written smaller after it: "/ 600", "of 400 h". */
  of?: string | undefined;
  /** A bar to the target, with its percent (or other short text) beside it. */
  meter?: { percent: number; label: string; text: string } | undefined;
  note?: ReactNode;
  spark?: number[] | undefined;
}) {
  return (
    <div className="kpi">
      <p className="kpi__label">
        <IconTile name={icon} {...(tone ? { tone } : {})} size={22} />
        <span>{label}</span>
      </p>
      <div className="kpi__body">
        <p className="kpi__value">
          {value}
          {of ? <span className="kpi__of"> {of}</span> : null}
        </p>
        {spark ? <Sparkline values={spark} /> : null}
      </div>
      {/* Always four parts, so the figures of a strip line up row by row (a subgrid). */}
      {meter ? (
        <div className="kpi__meter">
          <Meter percent={meter.percent} label={meter.label} />
          <span>{meter.text}</span>
        </div>
      ) : (
        <span className="kpi__none" />
      )}
      {note ? <p className="kpi__note">{note}</p> : <span className="kpi__none" />}
    </div>
  );
}

export interface DaySeries<T> {
  label: string;
  /** Colour class for the bar and its legend swatch, e.g. "series--approved". */
  className: string;
  value: (day: T) => number;
}

export interface DayColumn<T> {
  label: string;
  value: (day: T) => ReactNode;
}

const PAD_L = 36;
const PAD_B = 22;
const PAD_R = 16;

/** A round number at or above n for the top of an axis: 1, 2, 2.5 or 5 times a power of ten. */
function roundUp(n: number): number {
  const power = 10 ** Math.floor(Math.log10(n));
  const step = [1, 2, 2.5, 5, 10].find((f) => n <= f * power + 1e-9) ?? 10;
  return step * power;
}

/** The width of an element in pixels, followed as it changes (a first guess until measured, and
 * in tests, where nothing is laid out). */
function useWidth(guess: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(guess);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver((entries) => {
      const w = Math.round(entries[0]?.contentRect.width ?? 0);
      if (w > 0) setWidth(w);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}

/** Bars per day, stacked by series, with an optional daily target line, drawn at the panel's own
 * width so its text keeps its size. Hovering a day shows its numbers; "Show as a table" gives
 * every day's numbers for screen readers and copying. */
export function DayChart<T extends { day: string }>({
  title,
  days,
  series,
  columns,
  target = 0,
  emptyText,
  wholeNumbers = false,
  height = 200,
}: {
  title: string;
  days: T[];
  series: DaySeries<T>[];
  columns: DayColumn<T>[];
  target?: number;
  emptyText: string;
  /** Counts (calls) rather than amounts (hours): grid lines on whole numbers. */
  wholeNumbers?: boolean;
  /** The drawing's height in pixels. */
  height?: number;
}) {
  const H = height;
  const { ref, width: W } = useWidth(640);
  const [hover, setHover] = useState<number | null>(null);
  const titleId = useId();
  const totals = days.map((d) => series.reduce((n, s) => n + s.value(d), 0));
  const max = Math.max(target, ...totals);
  const empty = totals.every((n) => n === 0);
  const top = max > 0 ? roundUp(max * 1.1) : 1;
  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_B - 8;
  const slot = plotW / Math.max(1, days.length);
  const barW = Math.max(2, Math.min(16, slot * 0.62));
  const y = (v: number) => 8 + plotH - (v / top) * plotH;
  // Round numbers on the axis: 0, half way and the top (no half way for a count that is odd).
  const ticks = wholeNumbers && top % 2 !== 0 ? [0, top] : [0, top / 2, top];
  const labelEvery = days.length > 31 ? 14 : days.length > 14 ? 7 : 1;
  const shown = hover === null ? null : days[hover];
  const long = { weekday: "short", day: "numeric", month: "short" } as const;
  return (
    <figure className="chart" aria-labelledby={titleId}>
      <figcaption className="chart__head">
        <h2 id={titleId}>{title}</h2>
        <ul className="legend">
          {series.map((s) => (
            <li key={s.label}>
              <span className={`legend__swatch ${s.className}`} aria-hidden="true" />
              {s.label}
            </li>
          ))}
          {target > 0 ? (
            <li>
              <span className="legend__line" aria-hidden="true" />
              Daily target
            </li>
          ) : null}
        </ul>
      </figcaption>
      <div className="chart__plot" ref={ref}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width={W}
          height={H}
          role="img"
          aria-label={`${title}, see the table below`}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line className="chart__grid" x1={PAD_L} x2={W - PAD_R} y1={y(t)} y2={y(t)} />
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
                {series.map((s) => {
                  const n = s.value(d);
                  if (n <= 0) return null;
                  const y1 = y(base);
                  const y2 = y(base + n);
                  const gap = base > 0 ? 2 : 0;
                  base += n;
                  return (
                    <rect
                      key={s.label}
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
          <line className="chart__axis" x1={PAD_L} x2={W - PAD_R} y1={y(0)} y2={y(0)} />
          {target > 0 ? (
            <line
              className="chart__target"
              x1={PAD_L}
              x2={W - PAD_R}
              y1={y(target)}
              y2={y(target)}
            />
          ) : null}
        </svg>
        {empty ? (
          <p className="chart__empty">
            <span>{emptyText}</span>
          </p>
        ) : null}
        {shown ? (
          <div
            className="chart__tooltip"
            style={{ left: `${((PAD_L + (hover ?? 0) * slot + slot / 2) / W) * 100}%` }}
            aria-hidden="true"
          >
            <strong>{dayLabel(shown.day, long)}</strong>
            {columns.map((c) => (
              <span key={c.label}>
                {c.label}: {c.value(shown)}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      <details className="chart__table">
        <summary>Show as a table</summary>
        <DataTable label={title}>
          <thead>
            <tr>
              <th scope="col">Day</th>
              {columns.map((c) => (
                <th key={c.label} scope="col">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...days].reverse().map((d) => (
              <tr key={d.day}>
                <td>{dayLabel(d.day, long)}</td>
                {columns.map((c) => (
                  <td key={c.label}>{c.value(d)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </DataTable>
      </details>
    </figure>
  );
}

export interface DonutPart {
  key: string;
  label: ReactNode;
  n: number;
  /** A CSS colour for the slice and its legend swatch. */
  color: string;
  /** A second line under the label (what the slice is made of). */
  detail?: ReactNode;
}

/** A whole split into parts: a ring with the total in its middle, and beside it the legend as a
 * table (each part's count and share), which is also the chart's text for screen readers. */
export function Donut({
  label,
  parts,
  unit,
  emptyText,
}: {
  /** The legend table's name. */
  label: string;
  parts: DonutPart[];
  /** What the total in the middle counts: "tasks". */
  unit: string;
  emptyText: string;
}) {
  const total = parts.reduce((n, p) => n + p.n, 0);
  if (total === 0) return <p className="muted">{emptyText}</p>;
  const r = 46;
  const c = 2 * Math.PI * r;
  const drawn = parts.filter((p) => p.n > 0);
  // A 2px gap of the panel's colour between slices (none when one slice is the whole ring).
  const gap = drawn.length > 1 ? 2 : 0;
  const lengths = drawn.map((p) => (p.n / total) * c);
  // Where each slice starts: the lengths of the slices before it.
  const starts = lengths.map((_, i) => lengths.slice(0, i).reduce((a, b) => a + b, 0));
  return (
    <div className="donut">
      <svg className="donut__ring" viewBox="0 0 120 120" aria-hidden="true">
        <circle cx="60" cy="60" r={r} className="donut__track" />
        {drawn.map((p, i) => (
          <circle
            key={p.key}
            cx="60"
            cy="60"
            r={r}
            fill="none"
            strokeWidth="16"
            stroke={p.color}
            strokeDasharray={`${Math.max(0.5, (lengths[i] ?? 0) - gap)} ${c}`}
            strokeDashoffset={-(starts[i] ?? 0)}
            transform="rotate(-90 60 60)"
          />
        ))}
        <text x="60" y="60" textAnchor="middle" className="donut__total">
          {total}
        </text>
        <text x="60" y="76" textAnchor="middle" className="donut__unit">
          {unit}
        </text>
      </svg>
      <DataTable label={label} className="legend-table">
        <thead className="sr-only">
          <tr>
            <th scope="col">Part</th>
            <th scope="col">Count</th>
            <th scope="col">Share</th>
          </tr>
        </thead>
        <tbody>
          {parts.map((p) => (
            <tr key={p.key}>
              <th scope="row">
                <span className="legend-table__name">
                  <span
                    className="legend__swatch"
                    style={{ background: p.color }}
                    aria-hidden="true"
                  />
                  {p.label}
                </span>
                {p.detail ? <span className="legend-table__detail">{p.detail}</span> : null}
              </th>
              <td className="num">{p.n}</td>
              <td className="num muted">{Math.round((p.n / total) * 100)}%</td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </div>
  );
}

/** A whole in a few parts as one thin bar, with each part's name and count listed under it (the
 * list is the text; the bar only draws it). */
export function SplitBar({ title, parts }: { title: string; parts: DonutPart[] }) {
  const total = parts.reduce((n, p) => n + p.n, 0);
  return (
    <div className="splitbar">
      <p className="splitbar__title">
        {title}
        <span>{total}</span>
      </p>
      <div className="splitbar__bar" aria-hidden="true">
        {parts
          .filter((p) => p.n > 0)
          .map((p) => (
            <span key={p.key} style={{ flexGrow: p.n, background: p.color }} />
          ))}
      </div>
      <ul className="splitbar__legend">
        {parts.map((p) => (
          <li key={p.key}>
            <span className="legend__swatch" style={{ background: p.color }} aria-hidden="true" />
            <span className="splitbar__name">{p.label}</span>
            <span className="splitbar__n">{p.n}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A bar in a table cell: the actual share, with a tick where the target is. The numbers are in
 * the same row as text. `max` is the scale's end (the largest share in the section). */
export function TargetBar({
  value,
  target,
  max,
}: {
  value: number;
  target: number | null;
  max: number;
}) {
  const at = (n: number) => `${max > 0 ? Math.min(100, (n / max) * 100) : 0}%`;
  return (
    <span className="tbar" aria-hidden="true">
      <span className="tbar__fill" style={{ width: at(value) }} />
      {target !== null ? <span className="tbar__mark" style={{ left: at(target) }} /> : null}
    </span>
  );
}

/** A number with a light bar behind it, as long as its share of the column's largest. */
export function CellBar({
  value,
  max,
  children,
}: {
  value: number;
  max: number;
  children: ReactNode;
}) {
  const width = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <span className="cellbar" style={{ "--w": `${width}%` } as CSSProperties}>
      {children}
    </span>
  );
}

/** Two columns: a name and its value, one per row (a panel's few figures). */
export function KeyTable({
  label,
  rows,
}: {
  label: string;
  rows: { label: ReactNode; value: ReactNode; key?: string }[];
}) {
  return (
    <DataTable label={label} className="key-table">
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.key ?? (typeof r.label === "string" ? r.label : i)}>
            <th scope="row">{r.label}</th>
            <td className="num">{r.value}</td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}

export interface MatrixColumn<R> {
  key: string;
  label: ReactNode;
  num?: boolean;
  cell: (row: R) => ReactNode;
}

export interface MatrixSection<R> {
  key: string;
  title: string;
  /** Muted words after the section's title: what its numbers are of. */
  note?: ReactNode;
  rows: R[];
  /** Said in the section when it has no rows. */
  empty?: ReactNode;
}

/** One table with its rows in named sections (age bands, gender, ...; or reasons by kind),
 * and optionally a band of column groups above the column headings. */
export function MatrixTable<R>({
  label,
  head,
  columns,
  sections,
  rowKey,
  rowLabel,
  groups,
  quietHead = false,
}: {
  label: string;
  /** The first column's heading (the row names). */
  head: string;
  columns: MatrixColumn<R>[];
  sections: MatrixSection<R>[];
  rowKey: (row: R) => string;
  rowLabel: (row: R) => ReactNode;
  groups?: { label: string; span: number; tone?: Tone }[];
  /** The column headings for screen readers only (the section titles say enough). */
  quietHead?: boolean;
}) {
  const id = useId();
  const width = columns.length + 1;
  return (
    <DataTable label={label} className="matrix">
      <thead className={quietHead ? "sr-only" : undefined}>
        {groups ? (
          <tr className="matrix__groups">
            <td />
            {groups.map((g) => (
              <th
                key={g.label}
                scope="colgroup"
                colSpan={g.span}
                className={g.tone ? `matrix__band matrix__band--${g.tone}` : "matrix__band"}
              >
                {g.label}
              </th>
            ))}
          </tr>
        ) : null}
        <tr>
          <th scope="col">{head}</th>
          {columns.map((c) => (
            <th key={c.key} scope="col" className={c.num ? "num" : undefined}>
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      {sections.map((s) => {
        const sid = `${id}-${s.key}`;
        return (
          <tbody key={s.key} aria-labelledby={sid}>
            <tr className="matrix__section">
              <th scope="rowgroup" colSpan={width}>
                <span id={sid} className="matrix__title">
                  {s.title}
                </span>
                {s.note ? <span className="matrix__note">{s.note}</span> : null}
              </th>
            </tr>
            {s.rows.length === 0 && s.empty ? (
              <tr className="matrix__empty">
                <td colSpan={width}>{s.empty}</td>
              </tr>
            ) : (
              s.rows.map((r) => (
                <tr key={rowKey(r)}>
                  <th scope="row">{rowLabel(r)}</th>
                  {columns.map((c) => (
                    <td key={c.key} className={c.num ? "num" : undefined}>
                      {c.cell(r)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        );
      })}
    </DataTable>
  );
}

// Figures and charts shared by the dashboard and the Phone calls page: a key figure tile, bars per
// day (stacked series, a hover note and the same numbers as a table), and rows of thin bars.
import { useId, useState, type ReactNode } from "react";

import { dayLabel } from "../../lib/format";
import { DataTable } from "../DataTable";
import { IconTile, type IconName } from "../Icon";
import "./charts.css";

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

/** A key figure: label, big value, a note, and optionally a ring (percent) or a sparkline. */
export function Stat({
  icon,
  tone = "blue",
  label,
  value,
  note,
  ring,
  spark,
}: {
  icon: IconName;
  tone?: Tone;
  label: string;
  value: string;
  note?: string | undefined;
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

const W = 1000;
const H = 250;
const PAD_L = 40;
const PAD_B = 26;

/** Bars per day, stacked by series, with an optional daily target line. Hovering a day shows its
 * numbers; "Show as a table" gives every day's numbers for screen readers and copying. */
export function DayChart<T extends { day: string }>({
  title,
  days,
  series,
  columns,
  target = 0,
  emptyText,
  wholeNumbers = false,
}: {
  title: string;
  days: T[];
  series: DaySeries<T>[];
  columns: DayColumn<T>[];
  target?: number;
  emptyText: string;
  /** Counts (calls) rather than amounts (hours): grid lines on whole numbers. */
  wholeNumbers?: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const titleId = useId();
  const totals = days.map((d) => series.reduce((n, s) => n + s.value(d), 0));
  const max = Math.max(target, ...totals);
  const empty = totals.every((n) => n === 0);
  const top = max > 0 ? (wholeNumbers ? Math.ceil(max * 1.15) : max * 1.15) : 1;
  const plotW = W - PAD_L;
  const plotH = H - PAD_B - 8;
  const slot = plotW / Math.max(1, days.length);
  const barW = Math.max(3, Math.min(18, slot - 4));
  const y = (v: number) => 8 + plotH - (v / top) * plotH;
  // Each tick once: with very small totals the three round to the same number.
  const round = (t: number) => (wholeNumbers ? Math.round(t) : Math.round(t * 10) / 10);
  const ticks = Array.from(new Set([0, top / 2, top].map(round)));
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
      <div className="chart__plot">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}, see the table below`}>
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
          <line className="chart__axis" x1={PAD_L} x2={W} y1={y(0)} y2={y(0)} />
          {target > 0 ? (
            <line className="chart__target" x1={PAD_L} x2={W} y1={y(target)} y2={y(target)} />
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

export interface BarRow {
  key: string;
  label: ReactNode;
  n: number;
  note?: string;
  /** A colour for this row's bar (CSS colour); the theme's blue when not given. */
  color?: string;
}

/** Rows of "label, thin bar, number": reasons, problems, statuses, the funnel. */
export function Bars({
  rows,
  max,
  empty,
  wide = false,
}: {
  rows: BarRow[];
  max?: number;
  empty: string;
  /** Longer labels (sentences rather than single words). */
  wide?: boolean;
}) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.n));
  if (rows.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ul className={wide ? "bars bars--wide" : "bars"}>
      {rows.map((r) => (
        <li key={r.key}>
          <span>{r.label}</span>
          <span className="bars__track" aria-hidden="true">
            <span
              style={{
                width: `${top > 0 ? (r.n / top) * 100 : 0}%`,
                ...(r.color ? { background: r.color } : {}),
              }}
            />
          </span>
          <span className="bars__value">
            {r.n}
            {r.note ? <span className="muted bars__note"> {r.note}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

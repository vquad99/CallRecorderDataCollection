// Dates, times and amounts as people read them: Indian English, in India time, the same on
// every page whatever the computer's own settings are (D-126). A date with its time names the
// zone ("IST"), so someone outside India never takes it for their own time; a time alone sits
// under one that does.
const LOCALE = "en-IN";
const ZONE = "Asia/Kolkata";

const dateTime = new Intl.DateTimeFormat(LOCALE, {
  timeZone: ZONE,
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});
const dateOnly = new Intl.DateTimeFormat(LOCALE, {
  timeZone: ZONE,
  day: "numeric",
  month: "short",
  year: "numeric",
});
const timeOnly = new Intl.DateTimeFormat(LOCALE, {
  timeZone: ZONE,
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
});

/** "17 Nov 2026, 1:57 pm IST"; "-" when there is no time. */
export const when = (iso: string | null | undefined): string =>
  iso ? dateTime.format(new Date(iso)) : "-";

/** "17 Nov 2026". */
export const day = (iso: string): string => dateOnly.format(new Date(iso));

/** "1:57:08 pm" (in India time, like the date and time it is shown under). */
export const time = (iso: string): string => timeOnly.format(new Date(iso));

/** A calendar day the server counted ("2026-11-17", already in India time), e.g. "17 Nov". */
export const dayLabel = (isoDay: string, opts: Intl.DateTimeFormatOptions): string =>
  new Date(`${isoDay}T00:00:00Z`).toLocaleDateString(LOCALE, { ...opts, timeZone: "UTC" });

/** A day typed in a date box, once it is a real one ("2026-11-01"); "" while its year is still
 * being typed. A browser fills a year typed so far with zeros (0002, 0020, 0202): asking the
 * server for those days, or calling them before the first day, would only flash errors. */
export const typedDay = (value: string | null | undefined): string =>
  value && value >= "2000-01-01" ? value : "";

/** Seconds as a stopwatch shows them: "4:07". */
export const clock = (seconds: number): string =>
  `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

/** A length: seconds under a minute, then minutes, then hours. */
export function duration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "-";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

/** Hours of audio: "12 h", "2.5 h", "40 min". */
export const hours = (h: number): string =>
  h >= 10 ? `${h.toFixed(0)} h` : h >= 1 ? `${h.toFixed(1)} h` : `${Math.round(h * 60)} min`;

/** A file size: "512 KB", "1.4 GB". */
export function bytes(n: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

const inr = new Intl.NumberFormat(LOCALE, { style: "currency", currency: "INR" });

/** Rupees as people read them: "₹1,23,456.50". Amounts travel as text with two places. */
export const rupees = (amount: string | number): string => inr.format(Number(amount));

/** "1 recording", "3 recordings". */
export const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? "" : "s"}`;

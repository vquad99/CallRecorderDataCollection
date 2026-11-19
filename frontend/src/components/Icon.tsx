// Icons are Phosphor Icons (MIT, one consistent family), generated as path data by
// scripts/gen-icons.mjs so the app ships only the icons and weights it uses. Decorative only: every
// icon is hidden from screen readers, so each control keeps its text label as its accessible name.
//
// Colour (D-141): an icon has one colour for what it means, the same on every page: files to
// download in their own colour (CSV green, ZIP amber, audio violet), deleting and rejecting red,
// holding amber, editing and emailing blue. It is drawn two-tone, a soft fill under the outline.
// On a filled button the icon takes the button's text colour. Arrows, close and menu have none.
import { ICON_PATHS } from "./icons.generated";

export type IconName = keyof typeof ICON_PATHS;
type Weight = "regular" | "fill" | "bold";
export type Tone = "blue" | "teal" | "violet" | "amber" | "rose" | "green" | "slate";

const TONE_OF: Partial<Record<IconName, Tone>> = {
  // the sections of the side menu, and their page titles
  chart: "blue",
  projects: "amber",
  tasks: "teal",
  phone: "green",
  people: "violet",
  users: "blue",
  settings: "slate",
  money: "green",
  audit: "slate",
  status: "teal",
  user: "blue",
  // files
  fileCsv: "green",
  table: "green",
  fileZip: "amber",
  fileAudio: "violet",
  fileText: "blue",
  fileUp: "blue",
  download: "blue",
  upload: "blue",
  // actions
  plus: "blue",
  pencil: "blue",
  mail: "blue",
  send: "blue",
  link: "blue",
  comment: "blue",
  refresh: "blue",
  play: "blue",
  userPlus: "blue",
  info: "blue",
  eye: "slate",
  history: "slate",
  copy: "slate",
  archive: "slate",
  logout: "slate",
  filterX: "slate",
  lock: "slate",
  id: "slate",
  pause: "amber",
  key: "amber",
  clock: "amber",
  warning: "amber",
  resume: "green",
  ok: "green",
  verified: "green",
  target: "teal",
  mic: "violet",
  waveform: "violet",
  trash: "rose",
  failed: "rose",
  prohibit: "rose",
  userMinus: "rose",
  phoneX: "rose",
  record: "rose",
  stop: "rose",
};

interface Shapes {
  regular: string;
  fill?: string;
  bold?: string;
  duo?: string;
}

export function Icon({
  name,
  size = 20,
  weight,
  tone,
}: {
  name: IconName;
  size?: number;
  /** Without a weight an icon is drawn two-tone (or plain, for arrows and the like). */
  weight?: Weight;
  /** "text" takes the colour of the text around it instead of the icon's own colour. */
  tone?: Tone | "text";
}) {
  const shapes: Shapes = ICON_PATHS[name];
  const colour = tone === "text" ? undefined : (tone ?? TONE_OF[name]);
  return (
    <svg
      className={colour ? `icon icon--${colour}` : "icon"}
      width={size}
      height={size}
      viewBox="0 0 256 256"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
    >
      {weight === undefined && shapes.duo ? (
        <>
          <path d={shapes.duo} opacity="0.2" />
          <path d={shapes.regular} />
        </>
      ) : (
        <path d={(weight && shapes[weight]) || shapes.regular} />
      )}
    </svg>
  );
}

/** A soft tile holding an icon in its colour: page titles, figures, card headings. */
export function IconTile({
  name,
  tone,
  size = 36,
}: {
  name: IconName;
  tone?: Tone;
  size?: number;
}) {
  return (
    <span
      className={`tile tile--${tone ?? TONE_OF[name] ?? "blue"}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <Icon name={name} size={Math.round(size * 0.55)} weight="fill" tone="text" />
    </span>
  );
}

const TONES: Tone[] = ["blue", "teal", "violet", "amber", "rose", "green"];

/** Initials on a colour picked from the name, so the same person or project keeps its colour. */
export function Avatar({ name, square = false }: { name: string; square?: boolean }) {
  const words = name
    .trim()
    .split(/[\s._-]+/)
    .filter(Boolean);
  const text = (
    (words[0]?.[0] ?? "?") + (words.length > 1 ? (words[1]?.[0] ?? "") : (words[0]?.[1] ?? ""))
  ).toUpperCase();
  let sum = 0;
  for (const ch of name) sum += ch.charCodeAt(0);
  return (
    <span
      className={`avatar avatar--${TONES[sum % TONES.length]}${square ? " avatar--square" : ""}`}
      aria-hidden="true"
    >
      {text}
    </span>
  );
}

/** The product mark: two voices as two bar groups on a blue tile. */
export function BrandMark({ size = 26 }: { size?: number }) {
  return (
    <svg
      className="brand__mark"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="32" height="32" rx="6" fill="var(--brand-ink)" />
      <g strokeWidth="2.6" strokeLinecap="round" fill="none">
        <path d="M8 14v4M12 10v12M16 13v6" stroke="#fff" />
        <path d="M20 9v14M24 13v6" stroke="var(--accent)" />
      </g>
    </svg>
  );
}

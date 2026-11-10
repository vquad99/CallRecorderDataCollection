// Icons are Phosphor Icons (MIT, one consistent family), generated as path data by
// scripts/gen-icons.mjs so the app ships only the icons and weights it uses. Decorative only: every
// icon is hidden from screen readers, so each control keeps its text label as its accessible name.
import { ICON_PATHS } from "./icons.generated";

export type IconName = keyof typeof ICON_PATHS;
type Weight = "regular" | "fill" | "bold";

export function Icon({
  name,
  size = 20,
  weight = "regular",
}: {
  name: IconName;
  size?: number;
  weight?: Weight;
}) {
  const shapes: Partial<Record<Weight, string>> = ICON_PATHS[name];
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 256 256"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
    >
      <path d={shapes[weight] ?? shapes.regular} />
    </svg>
  );
}

type Tone = "blue" | "teal" | "violet" | "amber" | "rose" | "green" | "slate";

/** A coloured tile holding an icon: page titles, figures, list rows. */
export function IconTile({
  name,
  tone = "blue",
  size = 36,
}: {
  name: IconName;
  tone?: Tone;
  size?: number;
}) {
  return (
    <span className={`tile tile--${tone}`} style={{ width: size, height: size }} aria-hidden="true">
      <Icon name={name} size={Math.round(size * 0.55)} weight="fill" />
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

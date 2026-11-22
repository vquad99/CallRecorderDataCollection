// A project's targets on the Rules tab (D-148): the Konkani-region districts of the first client
// (NLTM), which "Use the Konkani-region districts" fills in, the default age bands ("Reset to the
// default age bands"), and the checks the targets must pass before they are saved (the server
// checks again). The districts are written once more in the server (projects/targets.py); a
// backend test checks that the two match.
import type { AgeBand, TargetDistrict } from "../../api/projects";

export const CLIENT_DISTRICTS: readonly TargetDistrict[] = [
  { state: "Goa", district: "North Goa" },
  { state: "Goa", district: "South Goa" },
  { state: "Karnataka", district: "Uttara Kannada" },
  { state: "Karnataka", district: "Udupi" },
  { state: "Karnataka", district: "Dakshina Kannada" },
  { state: "Maharashtra", district: "Sindhudurg" },
  { state: "Maharashtra", district: "Ratnagiri" },
  { state: "Maharashtra", district: "Raigad" },
];

/** The default age bands (the first client's), as a new project starts. */
export const CLIENT_AGE_BANDS: readonly AgeBand[] = [
  { from: 20, to: 30, percent: 40 },
  { from: 30, to: 40, percent: 30 },
  { from: 40, to: 50, percent: 20 },
  { from: 50, to: 60, percent: 10 },
];

export const PAUSE_LIMITS = { min: 1, max: 30 };
export const MAX_BANDS = 12;
export const MAX_DISTRICTS = 100;

const whole = (n: number, low: number, high: number) =>
  Number.isInteger(n) && n >= low && n <= high;

/** What is wrong with percents that should add up to 100, or null. */
export function percentsProblem(values: readonly number[]): string | null {
  if (values.some((v) => !whole(v, 0, 100))) return "Each percent is a whole number from 0 to 100.";
  const total = values.reduce((sum, v) => sum + v, 0);
  return values.length > 0 && total !== 100 ? `The percents add up to ${total}, not 100.` : null;
}

/** What is wrong with the age bands, or null (no bands at all is fine: no age target). */
export function bandsProblem(bands: readonly AgeBand[]): string | null {
  if (bands.length > MAX_BANDS) return `At most ${MAX_BANDS} age bands.`;
  for (const [i, b] of bands.entries()) {
    if (!whole(b.from, 1, 120) || !whole(b.to, 1, 120))
      return `Age band ${i + 1}: ages are whole numbers from 1 to 120.`;
    if (b.from >= b.to) return `Age band ${i + 1}: the first age must be below the last.`;
  }
  const sorted = [...bands].sort((a, b) => a.from - b.from);
  for (let i = 1; i < sorted.length; i++) {
    const before = sorted[i - 1];
    const after = sorted[i];
    if (before && after && after.from < before.to)
      return `Age bands ${before.from}-${before.to} and ${after.from}-${after.to} overlap.`;
  }
  return percentsProblem(bands.map((b) => b.percent));
}

/** What is wrong with the districts, or null. */
export function districtsProblem(districts: readonly TargetDistrict[]): string | null {
  if (districts.length > MAX_DISTRICTS) return `At most ${MAX_DISTRICTS} districts.`;
  const seen = new Set<string>();
  for (const [i, d] of districts.entries()) {
    const name = d.district.split(/\s+/).filter(Boolean).join(" ");
    if (!d.state || !name) return `District ${i + 1}: choose the state and type the district.`;
    if (name.length > 100) return `District ${i + 1}: at most 100 characters.`;
    const key = `${d.state.toLowerCase()}|${name.toLowerCase()}`;
    if (seen.has(key)) return `District ${i + 1}: ${name} is listed twice.`;
    seen.add(key);
  }
  return null;
}

/** A pause limit as typed, or null when it is not a whole number from 1 to 30. */
export const pauseLimitOf = (text: string): number | null => {
  const n = Number(text);
  return text.trim() !== "" && whole(n, PAUSE_LIMITS.min, PAUSE_LIMITS.max) ? n : null;
};

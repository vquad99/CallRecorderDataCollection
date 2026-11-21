// The moderator's reminders on a project's Rules tab (D-147): the first client's text (Konkani,
// NLTM), which "Reset to the client's text" puts back, and the checks a list must pass before it
// is saved (the server checks again). The same text is written once more in the server
// (projects/moderation.py); a backend test checks that the two match.
import type { Reminders } from "../../api/projects";

export const CLIENT_REMINDERS: Reminders = {
  speaker_id: true,
  topics: [
    "daily activities",
    "education",
    "agriculture",
    "food and cooking",
    "travel",
    "shopping",
    "health and fitness in general",
    "weather",
    "work and hobbies",
  ],
  avoid: [
    "politics",
    "religion",
    "obscene talk",
    "hate or killing",
    "other sensitive topics",
    "personal information",
  ],
  face_to_face: [
    "Record in a quiet place; both speakers stay in one place (sitting or standing).",
    "Place the recording device between the two speakers, no more than 2.5 feet from each mouth, and do not move it.",
  ],
  telephony: [
    "Each speaker is in a quiet place and stays in one place (sitting or standing).",
    "Hold the handset near the mouth and keep the loudspeaker off.",
    "No ringtones or notification sounds during the call.",
  ],
};

/** The lists of lines, with their labels on the Rules tab. */
export const REMINDER_LISTS: readonly {
  key: Exclude<keyof Reminders, "speaker_id">;
  label: string;
  hint: string;
}[] = [
  { key: "topics", label: "Talk about", hint: "One topic per line, shown after “Talk about:”." },
  { key: "avoid", label: "Avoid", hint: "One per line, shown after “Avoid:”." },
  {
    key: "face_to_face",
    label: "Face-to-face tips",
    hint: "One tip per line, shown on the recorder.",
  },
  {
    key: "telephony",
    label: "Phone call tips",
    hint: "One tip per line, shown on the call card.",
  },
];

export const MAX_LINES = 20;
export const MAX_LINE = 200;

/** A box's text as the lines it holds: spaces tidied, empty lines dropped. */
export const linesOf = (text: string) =>
  text
    .split("\n")
    .map((line) => line.split(/\s+/).filter(Boolean).join(" "))
    .filter(Boolean);

/** What is wrong with a box's lines, or null. */
export function linesProblem(text: string): string | null {
  const lines = linesOf(text);
  if (lines.length > MAX_LINES) return `At most ${MAX_LINES} lines.`;
  const long = lines.findIndex((line) => line.length > MAX_LINE);
  return long >= 0 ? `Line ${long + 1} is longer than ${MAX_LINE} characters.` : null;
}

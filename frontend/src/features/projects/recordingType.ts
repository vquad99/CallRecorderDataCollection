// One recording type per project (D-153): face-to-face conversations or phone calls, never both.
// A project made before D-153 may still allow both until its Overview is saved with one.
import type { ProjectSummary } from "../../api/projects";

export type RecordingMode = "FACE_TO_FACE" | "TELEPHONY";

/** The project's one recording type; null for a project made before D-153 that allows both. */
export function onlyMode(
  p: Pick<ProjectSummary, "allows_telephony" | "allows_face_to_face">,
): RecordingMode | null {
  if (p.allows_telephony && p.allows_face_to_face) return null;
  if (p.allows_telephony) return "TELEPHONY";
  return p.allows_face_to_face ? "FACE_TO_FACE" : null;
}

/** "phone calls" or "face-to-face conversations", for sentences. */
export const MODE_WORDS: Record<RecordingMode, string> = {
  FACE_TO_FACE: "face-to-face conversations",
  TELEPHONY: "phone calls",
};

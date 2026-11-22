// The QC checklist on a project's Rules tab (D-146): the default list (the first client's, Konkani
// NLTM), which "Reset to the default list" puts back, and the checks a list must pass before it is
// saved (the server checks again). The same list is written once more in the server
// (audio_qc/checklist.py); a backend test checks that the two match.
import type { ChecklistItem } from "../../api/projects";

/** Conversation questions fail the recording on No; speaker questions are observations. */
const conversation = (key: string, question: string): ChecklistItem => ({
  key,
  question,
  scope: "conversation",
  fails_on: "no",
  required: true,
});
const speaker = (key: string, question: string): ChecklistItem => ({
  key,
  question,
  scope: "speaker",
  fails_on: null,
  required: true,
});

export const CLIENT_QC_CHECKLIST: readonly ChecklistItem[] = [
  conversation(
    "correct_speaker_ids",
    "Both speakers have unique IDs that match the registered participants",
  ),
  conversation("speaker_id_announced", "Each speaker clearly says their speaker ID at the start"),
  conversation("two_speakers", "The conversation is between exactly two speakers"),
  conversation("no_third_person", "No third person speaks or interrupts"),
  conversation("within_max_duration", "The conversation is within the maximum length (15 minutes)"),
  conversation("natural_conversation", "Natural conversation, not read from a script"),
  conversation(
    "suitable_topic",
    "A common topic: nothing political, religious, obscene, hateful or sensitive",
  ),
  conversation("no_personal_information", "Speakers do not share personal information"),
  conversation("quiet_environment", "Relatively quiet: no road, TV, crying babies or vehicles"),
  conversation("speakers_stationary", "Both speakers stay in one place (sitting or standing)"),
  conversation("short_fillers", "Fillers (uh, um) never last more than 3 seconds"),
  conversation("no_ringtone_overlap", "No ringtone or notification sound overlaps the speech"),
  conversation("correct_recording_mode", "Correctly recorded as face-to-face or phone call"),
  speaker("speech_intelligible", "Is speech intelligible?"),
  speaker("speech_slurring", "Is speech slurred?"),
  speaker("speech_stammering", "Is stammering present?"),
  speaker("is_non_native_speech_present", "Is non-native speech present?"),
  speaker("noisy_background", "Is background noise present?"),
  speaker("good_pace_of_speech", "Is the pace of speech good?"),
  speaker("is_this_natural_human_voice", "Is this a natural human voice?"),
  speaker("low_speaker_volume", "Is the speaker's volume low?"),
  speaker("speaker_far_from_microphone", "Is the speaker far from the microphone?"),
  speaker("microphone_saturation", "Is microphone saturation present?"),
  speaker("echo_in_audio", "Is echo present?"),
  speaker("read_speech", "Does the speech sound read?"),
  speaker("impromptu_speech", "Is the speech impromptu?"),
  speaker("notifications_telephonic_sounds", "Are notification or phone sounds present?"),
  speaker("speaker_breath_sounds", "Are breath sounds present?"),
];

export const MAX_ITEMS = 60;
export const MAX_KEY = 50;
export const MAX_QUESTION = 200;
const KEY_FORMAT = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;

/** What is wrong with a new question's key, or null. */
export function keyProblem(key: string, items: readonly ChecklistItem[]): string | null {
  if (!key) return "Type a key.";
  if (key.length > MAX_KEY || !KEY_FORMAT.test(key))
    return `Lowercase letters, digits and _ only (like speech_intelligible), at most ${MAX_KEY} characters.`;
  if (items.some((i) => i.key === key)) return `The key ${key} is already in the list.`;
  return null;
}

/** What is wrong with a question's words, or null. */
export function questionProblem(question: string): string | null {
  if (!question.trim()) return "Write the question.";
  if (question.length > MAX_QUESTION) return `At most ${MAX_QUESTION} characters.`;
  return null;
}

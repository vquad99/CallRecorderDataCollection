// How a project's exports are named in the client's delivery format (D-149): the Rules tab's
// Export card and the Export tab's note. backend/app/modules/projects/delivery.py holds the same
// rules and decides (a backend test checks that the client's name below matches its default).
import type { ConversationIdStyle, SpeakerIdStyle } from "../../api/projects";

/** The client's audio file name: both speaker IDs, their native PIN codes, the conversation ID. */
export const CLIENT_AUDIO_NAME = "{a}_{b}_{a_pin}_{b_pin}_{conversation}";
export const MAX_AUDIO_NAME = 100;
const TOKENS: readonly string[] = ["a", "b", "a_pin", "b_pin", "conversation"];
const TOKEN = /\{([^{}]*)\}/g;

const padded = (code: string) => String(Number(code.slice(1))).padStart(3, "0");

/** P000123 as a speaker ID: "123", or the code itself. */
export const speakerId = (code: string, style: SpeakerIdStyle) =>
  style === "CODE" ? code : padded(code);

/** T000045 as a conversation ID: "CON045", or the code itself. */
export const conversationId = (code: string, style: ConversationIdStyle) =>
  style === "CODE" ? code : `CON${padded(code)}`;

/** What is wrong with an audio file name, or null (the server checks again). */
export function audioNameProblem(pattern: string): string | null {
  const text = pattern.trim();
  if (!text) return `Write the audio file name, for example ${CLIENT_AUDIO_NAME}.`;
  if (text.length > MAX_AUDIO_NAME) return `At most ${MAX_AUDIO_NAME} characters.`;
  for (const [, token = ""] of text.matchAll(TOKEN)) {
    if (!TOKENS.includes(token))
      return `{${token}} is not a token: use {a}, {b}, {a_pin}, {b_pin} and {conversation}.`;
  }
  if (!/^[A-Za-z0-9_-]*$/.test(text.replace(TOKEN, "")))
    return "Between the tokens, use only letters, digits, _ and -.";
  if (!text.includes("{conversation}"))
    return "Include {conversation}, so that every name is unique.";
  return null;
}

/** The name the first conversation's audio would get: speakers P000001 and P000002 with native
 * PIN codes 570001 and 576101, task T000001. */
export function exampleAudioName(
  pattern: string,
  speakers: SpeakerIdStyle,
  conversations: ConversationIdStyle,
): string {
  const values: Record<string, string> = {
    a: speakerId("P000001", speakers),
    b: speakerId("P000002", speakers),
    a_pin: "570001",
    b_pin: "576101",
    conversation: conversationId("T000001", conversations),
  };
  return `${pattern.trim().replace(TOKEN, (_, token: string) => values[token] ?? "")}.wav`;
}

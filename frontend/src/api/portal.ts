// Participant personal page (D-067). The link's secret travels in a header, never in an address.
import { apiRequest, seg } from "./client";

export interface PortalSession {
  task_code: string;
  mode: "TELEPHONY" | "FACE_TO_FACE";
  day: string;
  state: string;
  minutes: number | null;
}

export interface PortalView {
  participant_code: string;
  display_name: string;
  dialect: string;
  phone_hint: string | null;
  project_name: string;
  language_code: string;
  /** The form they agreed to once they agreed (D-068); otherwise the project's current one. */
  consent_policy_version: string;
  consent_text: string;
  /** Their consent as it counts now; "I agree" is final (D-129). WITHDRAWN only from before.
   * UPLOADED: staff uploaded their signed form, in a project that takes them (D-144). */
  consent_status: "GIVEN" | "REFUSED" | "WITHDRAWN" | "UPLOADED" | null;
  /** When it was given: the answer, or the day the signed form came in. */
  consent_at: string | null;
  sessions: PortalSession[];
  accepted_minutes: number;
  recorded_minutes: number;
  payable_minutes: number;
  link_expires_at: string | null; // null on the Super Admin's view (D-100)
}

const head = (token: string) => ({ "X-Portal-Token": token });

export const getPortal = (token: string) =>
  apiRequest<PortalView>("/api/v1/portal/me", { headers: head(token) });
export const answerConsent = (token: string, decision: "GIVEN" | "REFUSED") =>
  apiRequest<PortalView>("/api/v1/portal/consent", {
    method: "POST",
    body: { decision },
    headers: head(token),
  });
/** The participant's page as they see it, for a Super Admin; read-only (D-100). */
export const getParticipantPage = (projectId: string, participantId: string) =>
  apiRequest<PortalView>(
    `/api/v1/projects/${seg(projectId)}/participants/${seg(participantId)}/page`,
  );

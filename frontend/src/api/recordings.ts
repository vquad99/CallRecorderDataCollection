import { apiDownload, apiRequest, ApiError } from "./client";

export interface Asset {
  id: string;
  kind: string;
  version: number;
  codec: string;
  sample_rate: number;
  bit_depth: number;
  channels: number;
  duration_ms: number;
  size_bytes: number;
  sha256: string;
  peak_dbfs: number | null;
  rms_dbfs: number | null;
  clip_pct: number;
  silence_pct: number;
}

export interface Recording {
  id: string;
  task_id: string;
  state: "RECORDING" | "INTERRUPTED" | "UPLOADED" | "PROCESSING" | "READY" | "FAILED" | "DISCARDED";
  native_sample_rate: number;
  channel_count: number;
  device_channel_count: number | null;
  channel_handling: string;
  echo_cancellation: boolean | null;
  noise_suppression: boolean | null;
  auto_gain_control: boolean | null;
  chunks_received: number;
  saved_seconds: number;
  interrupted: boolean;
  failure_reason: string | null;
  assets: Asset[];
}

export interface StartInfo {
  native_sample_rate: number;
  /** Channels the capture delivers; the original keeps all of them. */
  channel_count: number;
  /** What the browser reports for the microphone track (may differ, or be unknown). */
  device_channel_count: number | null;
  echo_cancellation: boolean | null;
  noise_suppression: boolean | null;
  auto_gain_control: boolean | null;
  device_label: string;
  user_agent: string;
}

export const listRecordings = (taskId: string) =>
  apiRequest<Recording[]>(`/api/v1/tasks/${taskId}/recordings`);
export const getRecording = (id: string) => apiRequest<Recording>(`/api/v1/recordings/${id}`);
export const startRecording = (taskId: string, body: StartInfo) =>
  apiRequest<Recording>(`/api/v1/tasks/${taskId}/recordings`, { method: "POST", body });
export const markInterrupted = (id: string, reason: string) =>
  apiRequest<Recording>(`/api/v1/recordings/${id}/interrupted`, {
    method: "POST",
    body: { reason },
  });
export const completeRecording = (id: string, chunkCount: number) =>
  apiRequest<Recording>(`/api/v1/recordings/${id}/complete`, {
    method: "POST",
    body: { chunk_count: chunkCount },
  });
export const discardRecording = (id: string, reason: string) =>
  apiRequest<Recording>(`/api/v1/recordings/${id}/discard`, { method: "POST", body: { reason } });
export const assetUrl = (id: string, purpose: "play" | "download") =>
  apiRequest<{ url: string; expires_in: number }>(`/api/v1/assets/${id}/url`, {
    method: "POST",
    body: { purpose },
  });

function csrf(): string {
  const match = document.cookie
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith("csrf_token="));
  return match ? decodeURIComponent(match.slice("csrf_token=".length)) : "";
}

/** Raw chunk upload (not JSON), with the checksum the server verifies. */
export async function putChunk(
  recordingId: string,
  seq: number,
  body: ArrayBuffer,
  sha256: string,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`/api/v1/recordings/${recordingId}/chunks/${seq}`, {
      method: "PUT",
      credentials: "include",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Content-SHA256": sha256,
        "X-CSRF-Token": csrf(),
      },
      body,
    });
  } catch {
    throw new ApiError({ status: 0, code: "NETWORK_ERROR", message: "Cannot reach the server" });
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    const retryAfter = Number(response.headers.get("Retry-After"));
    throw new ApiError({
      status: response.status,
      code: payload?.error?.code ?? `HTTP_${response.status}`,
      message: payload?.error?.message ?? "Upload failed",
      retryAfterSeconds: Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
    });
  }
}

/** The 16 kHz delivery file of a recording: face-to-face, or a phone call (D-101). */
export const DELIVERY_KINDS: readonly string[] = [
  "FTF_DERIVED_PCM",
  "TELEPHONY_DERIVED_PCM",
  "TELEPHONY_FINAL_STEREO",
];
export const deliveryAsset = (assets: readonly Asset[]): Asset | undefined =>
  assets.find((a) => DELIVERY_KINDS.includes(a.kind));

/** Saves the delivery file and, with it, the consent record (D-068) and the details file with
 * every measurement and the audio check (D-079). */
export async function downloadWithConsent(recording: Recording, taskCode: string): Promise<void> {
  const final = deliveryAsset(recording.assets);
  if (!final) throw new ApiError({ status: 404, code: "NOT_FOUND", message: "File not found" });
  const { url } = await assetUrl(final.id, "download");
  const link = document.createElement("a");
  link.href = url;
  link.rel = "noopener";
  link.click();
  await apiDownload(
    `/api/v1/recordings/${recording.id}/consent-form`,
    `consent_${taskCode}_${recording.id}.html`,
  );
  await apiDownload(
    `/api/v1/recordings/${recording.id}/metadata`,
    `metadata_${taskCode}_${recording.id}.json`,
  );
}

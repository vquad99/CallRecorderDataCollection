import { apiRequest, ApiError } from "./client";

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
  channel_count: number;
  channel_handling: string;
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
    throw new ApiError({
      status: response.status,
      code: payload?.error?.code ?? `HTTP_${response.status}`,
      message: payload?.error?.message ?? "Upload failed",
    });
  }
}

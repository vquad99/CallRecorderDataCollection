// Shared API client (FND-016): same-origin cookies, CSRF header on writes, one error type.

export interface ApiErrorInit {
  status: number;
  code: string;
  message: string;
  requestId?: string | null;
  details?: unknown;
  /** Seconds the server asked to wait before trying again (Retry-After), when it said. */
  retryAfterSeconds?: number | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: unknown;
  readonly retryAfterSeconds: number | null;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.requestId = init.requestId ?? null;
    this.details = init.details;
    this.retryAfterSeconds = init.retryAfterSeconds ?? null;
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  /** Non-2xx statuses whose JSON body is a normal answer (e.g. 503 from /health/ready). */
  acceptStatuses?: readonly number[];
  /** Extra request headers (the participant page sends its link secret this way). */
  headers?: Record<string, string>;
}

export const UNAUTHENTICATED_EVENT = "ccp:unauthenticated";
/** The server refused a request because this account must set up two-step sign-in first
 * (D-106): for example a role given while the person was already signed in. */
export const MFA_SETUP_EVENT = "ccp:mfa-setup-required";
const CSRF_COOKIE = "csrf_token";
const CSRF_HEADER = "X-CSRF-Token";

export function apiBase(): string {
  return import.meta.env.VITE_API_BASE_URL ?? "";
}

/** One page of a list the server pages through. */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

/** "?a=1&b=x" from the given values; empty and missing values are left out. */
export function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

// When the server last heard from this page. A session ends after some minutes without requests
// (D-122); the sign-out warning counts from here.
let lastActivity = Date.now();
/** The time (ms) of the last request that reached the server. */
export const lastApiActivity = (): number => lastActivity;
/** Note that the server was reached just now. */
export function markApiActivity(): void {
  lastActivity = Date.now();
}

function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) return decodeURIComponent(trimmed.slice(prefix.length));
  }
  return null;
}

async function parseJson(response: Response): Promise<unknown> {
  const type = response.headers.get("content-type") ?? "";
  if (!type.includes("application/json")) return null;
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function errorFromBody(response: Response, body: unknown): ApiError {
  const requestId = response.headers.get("X-Request-ID");
  if (body && typeof body === "object" && "error" in body) {
    const error = (body as { error: Record<string, unknown> }).error;
    return new ApiError({
      status: response.status,
      code: typeof error.code === "string" ? error.code : `HTTP_${response.status}`,
      message: typeof error.message === "string" ? error.message : response.statusText,
      requestId: typeof error.request_id === "string" ? error.request_id : requestId,
      details: error.details,
    });
  }
  return new ApiError({
    status: response.status,
    code: `HTTP_${response.status}`,
    message: response.statusText || "Request failed",
    requestId,
  });
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers[CSRF_HEADER] = csrf;
  }

  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, {
      method,
      headers,
      credentials: "include",
      ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
      ...(options.signal ? { signal: options.signal } : {}),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError({ status: 0, code: "NETWORK_ERROR", message: "Cannot reach the server" });
  }

  markApiActivity();
  const body = await parseJson(response);
  if (response.ok || options.acceptStatuses?.includes(response.status)) return body as T;
  const error = errorFromBody(response, body);
  if (error.status === 401 && !path.startsWith("/api/v1/auth/")) {
    // Lets the sign-in state react when a session ends mid-use (AUTH-016).
    window.dispatchEvent(new CustomEvent(UNAUTHENTICATED_EVENT, { detail: { code: error.code } }));
  }
  if (error.code === "MFA_SETUP_REQUIRED") window.dispatchEvent(new Event(MFA_SETUP_EVENT));
  throw error;
}

/** The file name a download's answer gives (Content-Disposition), if any. */
function attachmentName(response: Response): string | null {
  const header = response.headers.get("content-disposition") ?? "";
  return /filename="([^"]+)"/.exec(header)?.[1] ?? null;
}

/** Fetch a file (e.g. a CSV export) with the session cookie and hand it to the browser, under
 * `filename`, or else the name the server gave it. */
export async function apiDownload(path: string, filename?: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, { credentials: "include" });
  } catch {
    throw new ApiError({ status: 0, code: "NETWORK_ERROR", message: "Cannot reach the server" });
  }
  markApiActivity();
  if (!response.ok) throw errorFromBody(response, await parseJson(response));
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename ?? attachmentName(response) ?? "download";
  link.click();
  URL.revokeObjectURL(url);
}

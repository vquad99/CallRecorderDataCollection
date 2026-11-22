// Requirements: FND-016
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiDownload, apiRequest, UNAUTHENTICATED_EVENT } from "./client";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("apiRequest", () => {
  it("sends cookies and JSON accept header on GET", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiRequest("/api/v1/version")).resolves.toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/version");
    expect(init.credentials).toBe("include");
    expect((init.headers as Record<string, string>).Accept).toBe("application/json");
  });

  it("adds the CSRF header on writes when the cookie exists", async () => {
    document.cookie = "csrf_token=abc123";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);
    await apiRequest("/api/v1/things", { method: "POST", body: { a: 1 } });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("abc123");
    expect(headers["Content-Type"]).toBe("application/json");
    expect(init.body).toBe('{"a":1}');
  });

  it.each([401, 403, 409, 500])("maps a %i error body to ApiError", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(status, { error: { code: "X_CODE", message: "Nope", request_id: "rid-1" } }),
        ),
    );
    const error = await apiRequest("/api/v1/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status, code: "X_CODE", message: "Nope", requestId: "rid-1" });
  });

  it("falls back when the error body is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("bad gateway", { status: 502, headers: { "X-Request-ID": "rid-2" } }),
        ),
    );
    await expect(apiRequest("/api/v1/x")).rejects.toMatchObject({
      status: 502,
      code: "HTTP_502",
      requestId: "rid-2",
    });
  });

  it("reports a network failure as NETWORK_ERROR", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiRequest("/api/v1/x")).rejects.toMatchObject({
      status: 0,
      code: "NETWORK_ERROR",
    });
  });

  it("returns the body for accepted non-2xx statuses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(503, { status: "not_ready" })));
    await expect(apiRequest("/health/ready", { acceptStatuses: [503] })).resolves.toEqual({
      status: "not_ready",
    });
  });
});

describe("an ended session (AUTH-016)", () => {
  const ended = () =>
    jsonResponse(401, { error: { code: "UNAUTHENTICATED", message: "Sign in required" } });

  /** The codes of the sign-out events raised while `act` runs. */
  async function signOuts(act: () => Promise<unknown>): Promise<string[]> {
    const seen: string[] = [];
    const listen = (e: Event) => seen.push((e as CustomEvent<{ code: string }>).detail.code);
    window.addEventListener(UNAUTHENTICATED_EVENT, listen);
    try {
      await act().catch(() => undefined);
    } finally {
      window.removeEventListener(UNAUTHENTICATED_EVENT, listen);
    }
    return seen;
  }

  it("is announced by a request and by a download, so the page goes to sign-in", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => Promise.resolve(ended())),
    );
    expect(await signOuts(() => apiRequest("/api/v1/tasks"))).toEqual(["UNAUTHENTICATED"]);
    expect(await signOuts(() => apiDownload("/api/v1/projects/p1/export"))).toEqual([
      "UNAUTHENTICATED",
    ]);
    // A wrong password at sign-in is not a session that ended.
    expect(await signOuts(() => apiRequest("/api/v1/auth/login", { method: "POST" }))).toEqual([]);
  });

  it("gives a refused download as an error the page can show", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(422, { error: { code: "TOO_LARGE", message: "Too many", request_id: "r" } }),
        ),
    );
    await expect(apiDownload("/api/v1/calls/export")).rejects.toMatchObject({
      status: 422,
      code: "TOO_LARGE",
      message: "Too many",
      requestId: "r",
    });
  });
});

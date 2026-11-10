// Requirements: FTF-009, FTF-010, STOR-004, STOR-006
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import { ChunkUploader, isPermanent, retryDelay, sha256Hex, SIGNED_OUT_MESSAGE } from "./uploader";

const samples = (n: number, value = 0.25) => new Float32Array(n).fill(value);

describe("ChunkUploader", () => {
  it("cuts the stream into fixed chunks, in order, with each chunk's SHA-256", async () => {
    const sent: { seq: number; bytes: number; sha: string }[] = [];
    const up = new ChunkUploader(async (seq, body, sha) => {
      sent.push({ seq, bytes: body.byteLength, sha });
      expect(sha).toBe(await sha256Hex(body));
    }, 1000);
    up.push(samples(2500));
    expect(await up.finish()).toBe(3);
    expect(sent.map((s) => [s.seq, s.bytes])).toEqual([
      [0, 4000],
      [1, 4000],
      [2, 2000],
    ]);
  });

  it("retries a chunk after a network failure and reports the problem", async () => {
    const put = vi
      .fn()
      .mockRejectedValueOnce(new ApiError({ status: 0, code: "NETWORK_ERROR", message: "x" }))
      .mockResolvedValue(undefined);
    const problems: (string | null)[] = [];
    const up = new ChunkUploader(put, 100, { onProblem: (p) => problems.push(p) }, 1);
    up.push(samples(100));
    expect(await up.finish()).toBe(1);
    expect(put).toHaveBeenCalledTimes(2);
    expect(problems[0]).toMatch(/Connection problem/);
    expect(problems.at(-1)).toBeNull();
  });

  it("stops on a permanent rejection instead of retrying forever", async () => {
    const put = vi.fn().mockRejectedValue(
      new ApiError({
        status: 409,
        code: "RECORDING_CLOSED",
        message: "The recording is interrupted",
      }),
    );
    const up = new ChunkUploader(put, 100, {}, 1);
    up.push(samples(250));
    await expect(up.finish()).rejects.toMatchObject({ code: "RECORDING_CLOSED" });
    expect(put).toHaveBeenCalledTimes(1);
  });

  it("waits for a new sign-in instead of giving up when the session ends (O1)", async () => {
    const problems: (string | null)[] = [];
    let signedIn = false;
    const sent: number[] = [];
    const up = new ChunkUploader(
      async (seq) => {
        if (!signedIn) {
          signedIn = true; // the user signs in again in another tab
          throw new ApiError({ status: 401, code: "SESSION_EXPIRED", message: "expired" });
        }
        sent.push(seq);
      },
      1000,
      { onProblem: (p) => problems.push(p) },
      1,
    );
    up.push(samples(2000));
    expect(await up.finish()).toBe(2);
    expect(sent).toEqual([0, 1]);
    expect(problems[0]).toBe(SIGNED_OUT_MESSAGE);
    expect(problems.at(-1)).toBeNull();
  });
});

describe("retry rules (O1)", () => {
  const err = (status: number, retryAfterSeconds?: number) =>
    new ApiError({ status, code: "X", message: "x", retryAfterSeconds: retryAfterSeconds ?? null });

  it("gives up only when the part itself is wrong", () => {
    expect([401, 408, 429, 500, 503, 0].map((s) => isPermanent(err(s)))).toEqual(
      Array(6).fill(false),
    );
    expect([400, 409, 413, 422].map((s) => isPermanent(err(s)))).toEqual(Array(4).fill(true));
    expect(isPermanent(new TypeError("Failed to fetch"))).toBe(false);
  });

  it("waits as the server asks, doubles otherwise, and spreads retries", () => {
    const middle = () => 0.5;
    expect(retryDelay(0, err(503, 7), 1000, middle)).toBe(7000);
    expect(retryDelay(0, err(500), 1000, middle)).toBe(1000);
    expect(retryDelay(3, err(500), 1000, middle)).toBe(8000);
    expect(retryDelay(10, err(500), 1000, middle)).toBe(30_000);
    expect(retryDelay(10, err(401), 1000, middle)).toBe(10_000);
    expect(retryDelay(0, err(500), 1000, () => 0)).toBe(800);
    expect(retryDelay(0, err(500), 1000, () => 1)).toBe(1200);
  });
});

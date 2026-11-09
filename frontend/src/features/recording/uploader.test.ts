// Requirements: FTF-009, FTF-010, STOR-004, STOR-006
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import { ChunkUploader, sha256Hex } from "./uploader";

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
});

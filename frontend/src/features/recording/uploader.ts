// Cuts the sample stream into fixed-length chunks and uploads them in order, retrying each one
// until it is stored (FTF-009, FTF-010). Unsent chunks stay in memory only (D-005).
import { ApiError } from "../../api/client";

export interface UploaderEvents {
  onProgress?: (sent: number, waiting: number) => void;
  onProblem?: (message: string | null) => void;
}

type Put = (seq: number, body: ArrayBuffer, sha256: string) => Promise<void>;

export async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const SIGNED_OUT_MESSAGE =
  "Your session has ended. Sign in again in a new tab: recording goes on here and the waiting " +
  "parts are sent as soon as you are signed in.";
export const CONNECTION_MESSAGE =
  "Connection problem. Saved parts are kept and sending is retried.";

/** Answers that end the upload: the part itself is wrong, so sending it again cannot help. */
export function isPermanent(err: unknown): boolean {
  return (
    err instanceof ApiError &&
    err.status >= 400 &&
    err.status < 500 &&
    err.status !== 401 && // signed out: waits for a new sign-in (O1)
    err.status !== 408 &&
    err.status !== 429
  );
}

/**
 * How long to wait before the next try (O1): the server's Retry-After when it gave one,
 * otherwise doubling from `baseMs` up to 30 s; a signed-out pause re-checks every 10 s. A spread
 * of +/-20 % keeps many recorders from retrying at the same instant after an outage.
 */
export function retryDelay(
  attempt: number,
  err: unknown,
  baseMs: number,
  random: () => number = Math.random,
): number {
  let ms = Math.min(baseMs * 2 ** attempt, 30_000);
  if (err instanceof ApiError && err.status === 401) ms = Math.min(10 * baseMs, 10_000);
  if (err instanceof ApiError && err.retryAfterSeconds) ms = err.retryAfterSeconds * 1000;
  return Math.round(ms * (0.8 + 0.4 * random()));
}

export class ChunkUploader {
  private buffer: Float32Array;
  private filled = 0;
  private nextSeq = 0;
  private sent = 0;
  private queue: { seq: number; data: ArrayBuffer }[] = [];
  private running: Promise<void> | null = null;
  private fatal: ApiError | null = null;

  constructor(
    private readonly put: Put,
    readonly chunkSamples: number,
    private readonly events: UploaderEvents = {},
    private readonly retryBaseMs = 1000,
  ) {
    this.buffer = new Float32Array(chunkSamples);
  }

  get chunkCount(): number {
    return this.nextSeq;
  }

  push(samples: Float32Array): void {
    let offset = 0;
    while (offset < samples.length) {
      const take = Math.min(samples.length - offset, this.chunkSamples - this.filled);
      this.buffer.set(samples.subarray(offset, offset + take), this.filled);
      this.filled += take;
      offset += take;
      if (this.filled === this.chunkSamples) this.enqueueBuffer();
    }
  }

  /** Send whatever is buffered and wait until every chunk is stored. */
  async finish(): Promise<number> {
    if (this.filled > 0) this.enqueueBuffer();
    while (this.running) await this.running;
    if (this.fatal) throw this.fatal;
    return this.nextSeq;
  }

  private enqueueBuffer(): void {
    const data = this.buffer.slice(0, this.filled).buffer;
    this.queue.push({ seq: this.nextSeq++, data });
    this.buffer = new Float32Array(this.chunkSamples);
    this.filled = 0;
    this.events.onProgress?.(this.sent, this.queue.length);
    if (!this.running) this.running = this.drain().finally(() => (this.running = null));
  }

  private async drain(): Promise<void> {
    while (this.queue.length > 0) {
      const item = this.queue[0];
      if (!item) break;
      const hash = await sha256Hex(item.data);
      for (let attempt = 0; ; attempt++) {
        try {
          await this.put(item.seq, item.data, hash);
          this.events.onProblem?.(null);
          break;
        } catch (err) {
          if (isPermanent(err)) {
            this.fatal = err as ApiError;
            this.queue = [];
            this.events.onProblem?.((err as ApiError).message);
            return;
          }
          const signedOut = err instanceof ApiError && err.status === 401;
          this.events.onProblem?.(signedOut ? SIGNED_OUT_MESSAGE : CONNECTION_MESSAGE);
          await wait(retryDelay(attempt, err, this.retryBaseMs));
        }
      }
      this.queue.shift();
      this.sent += 1;
      this.events.onProgress?.(this.sent, this.queue.length);
    }
  }
}

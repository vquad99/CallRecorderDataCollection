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
          const permanent =
            err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 429;
          if (permanent) {
            this.fatal = err;
            this.queue = [];
            this.events.onProblem?.(err.message);
            return;
          }
          this.events.onProblem?.(
            "Connection problem. Saved parts are kept and sending is retried.",
          );
          await wait(Math.min(this.retryBaseMs * 2 ** attempt, 30_000));
        }
      }
      this.queue.shift();
      this.sent += 1;
      this.events.onProgress?.(this.sent, this.queue.length);
    }
  }
}

// AudioWorklet: copies raw microphone samples (32-bit float, the device's native rate) to the page in
// batches. Every channel the browser delivers is kept, interleaved frame by frame, so the stored
// original is exactly what was captured; the server makes the mono delivery file from channel 1
// (D-041, D-048). No processing of any kind happens here (D-003, AUDIO-004).
const FRAMES = 4096;

class RawCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.channels = 0; // fixed by the first block of real input
    this.batch = null;
    this.filled = 0;
    this.stopped = false;
  }

  process(inputs) {
    const input = inputs[0];
    if (this.stopped || !input || input.length === 0) return true;
    if (this.channels === 0) {
      this.channels = input.length;
      this.batch = new Float32Array(FRAMES * this.channels);
    }
    if (input.length !== this.channels) {
      // Interleaving a different layout into the same file would corrupt it: stop and say so.
      this.stopped = true;
      this.port.postMessage({ layoutChanged: { from: this.channels, to: input.length } });
      return true;
    }
    const frames = input[0].length;
    for (let i = 0; i < frames; i++) {
      for (let c = 0; c < this.channels; c++) this.batch[this.filled++] = input[c][i];
      if (this.filled === this.batch.length) {
        this.port.postMessage({ samples: this.batch, channels: this.channels });
        this.batch = new Float32Array(FRAMES * this.channels);
        this.filled = 0;
      }
    }
    return true;
  }
}

registerProcessor("raw-capture", RawCapture);

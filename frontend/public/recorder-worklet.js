// AudioWorklet: copies raw microphone samples (channel 0, 32-bit float, the device's native rate)
// to the page in batches. No processing of any kind happens here (D-003, AUDIO-004).
class RawCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.batch = new Float32Array(4096);
    this.filled = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channel = input[0];
      let offset = 0;
      while (offset < channel.length) {
        const take = Math.min(channel.length - offset, this.batch.length - this.filled);
        this.batch.set(channel.subarray(offset, offset + take), this.filled);
        this.filled += take;
        offset += take;
        if (this.filled === this.batch.length) {
          this.port.postMessage({ samples: this.batch, channels: input.length });
          this.batch = new Float32Array(4096);
          this.filled = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("raw-capture", RawCapture);

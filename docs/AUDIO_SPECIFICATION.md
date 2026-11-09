# Audio specification

Status: planned (Phase 0). Requirement IDs: AUDIO-*, FTF-*, AQC-*, TEL-016..017, TEL-026.

## 1. Targets

| Mode | Final file | Container | Codec | Rate | Bits | Channels | Mapping |
|---|---|---|---|---|---|---|---|
| Telephony | one per conversation | WAV (RIFF) | PCM signed 16-bit little-endian | 16 000 Hz | 16 | 2 | left = Participant A, right = Participant B |
| Face-to-face | one derived per session | WAV (RIFF) | PCM signed 16-bit little-endian | 16 000 Hz | 16 | 1 | - |

Never applied to any delivered file: noise suppression, normalization, compression (dynamic or lossy),
EQ, enhancement (AUDIO-004). QC measures; it never changes a file (AUDIO-018).

## 2. Telephony

1. Provider originals are fetched and stored unchanged as `PROVIDER_ORIGINAL_TRACK` (or
   `PROVIDER_ORIGINAL_MIXED`) with codec, sample rate and the provider's recording specification
   (AUDIO-012, AUDIO-013).
2. Only a provider that supplies genuinely separate participant tracks (or dual-channel with verified
   mapping) can satisfy the requirement. A mixed recording is never copied to two channels; the
   requirement is marked BLOCKED (AUDIO-011).
3. Separate tracks are aligned using provider timestamps and joined into stereo, A left and B right.
   If both tracks are already 16 kHz s16, the join copies samples exactly (TA-AUDIO-02). If they are
   not, the conversion is recorded step by step in `asset_processing_steps`.
4. Bandwidth honesty: ordinary phone calls are commonly narrowband (ITU-T G.711, 8 kHz). If the
   provider's tracks are 8 kHz, the 16 kHz final file is an up-sampled copy and the processing history
   says so; it is never described as native 16 kHz or "uncompressed end to end" (AUDIO-013). Whether the
   client accepts that is open (DECISIONS.md B-02).
5. Moderator introduction: excluded from the participant conversation (recording starts after consent)
   or stored separately as `CONSENT_RECORDING`, per the policy agreed at Gate 5 (AUDIO-008).

Example join for two genuinely separate, aligned tracks (runbook O; tested on fixtures before use):

```bash
ffmpeg -i participant_a.wav -i participant_b.wav \
  -filter_complex "[0:a]aresample=16000,aformat=sample_fmts=s16:channel_layouts=mono[a]; \
                   [1:a]aresample=16000,aformat=sample_fmts=s16:channel_layouts=mono[b]; \
                   [a][b]join=inputs=2:channel_layout=stereo[aout]" \
  -map "[aout]" -c:a pcm_s16le -ar 16000 final_stereo.wav
```

Gate 5 acceptance (TEL-026): A says "This is participant A.", B says "This is participant B."; inspect
left alone, right alone, both together, cross-channel leakage, alignment, duration, sample rate, bit
depth, PCM codec, moderator presence per policy, and energy above 4 kHz per channel.

## 3. Face-to-face

Capture (FTF-001..012):
1. Check browser support (`getUserMedia`, `AudioWorklet`); unsupported browsers get a clear message.
2. Ask for microphone permission only after a user action; list devices after permission; user picks one.
3. Show the project's audio rules, a live level meter, and a short test recording with playback.
4. Capture with `channelCount: 1`, `echoCancellation: false`, `noiseSuppression: false`,
   `autoGainControl: false`; store what the browser actually applied (`MediaStreamTrack.getSettings()`).
   Some devices still process audio in hardware or the operating system; that cannot be detected
   fully and is stated in the session metadata.
5. An AudioWorklet reads raw 32-bit float samples at the device's native rate (commonly 48 kHz).
   MediaRecorder is not used because its usual output (Opus in WebM) is lossy (D-003).
6. Samples are sent in ~5-second chunks during recording, each with a sequence number and SHA-256.
   Unsent chunks live in memory only; nothing is written to browser storage (D-005).
7. Interruption (tab closed, device asleep, network lost): the server keeps every acknowledged chunk
   and marks the recording interrupted; the user is told exactly how much was saved. No claim is made
   that recording continued (FTF-009).

Original asset (`BROWSER_ORIGINAL`): chunks joined server-side into WAV, 32-bit float, native rate,
mono. Never overwritten.

Derived asset (`FTF_DERIVED_PCM`), deterministic pipeline (AUDIO-019..022):
1. Inspect the original with ffprobe; store the result.
2. Decode with no filters other than the ones listed here.
3. Resample to 16 000 Hz with a documented high-quality resampler (proposed: FFmpeg `soxr`).
4. Mono: the capture is mono, so no downmix. If a source ever has two channels, the downmix method
   (which channel, or equal-weight average) is a project decision recorded before conversion.
5. Convert to signed 16-bit; the dither choice is fixed and recorded.
6. Write WAV; inspect independently with ffprobe; store tool, version, parameters and SHA-256.

Example (runbook O; exact parameters fixed in Phase 4 and recorded):

```bash
ffmpeg -i original.wav -af aresample=resampler=soxr -ar 16000 -ac 1 -c:a pcm_s16le derived_mono_16k.wav
```

Resampling 48 kHz to 16 kHz and reducing to 16 bits is not lossless. The derived file is labelled
derived, the original is kept, and the client's acceptance is open (DECISIONS.md B-03).

## 4. Validation record (AUDIO-017)

Stored for every final asset: file extension and actual container, codec / sample format, sample rate,
bit depth, channel count, duration, file size, peak level, clipping count and percentage, silence
percentage, RMS level, SHA-256, source recording ID, ordered processing history (tool, version,
parameters).

Independent inspection: `ffprobe -v error -show_streams -show_format <file>`.

## 5. Audio QC (AQC-*)

Read-only analysis. Thresholds come from `project_audio_rules`; the only initial default is
silence > 25 % flagged. Metrics: container, codec, sample rate, bit depth, channels, duration, size,
peak, RMS, clipping ratio, silence ratio, dynamic range, leakage indicator (stereo), duplicate check,
decode errors; SNR only with a validated method, otherwise null with the reason.
Outcomes: PASS, FAIL, NEEDS_REVIEW with reason code and comment. Fixtures: TEST_PLAN.md section 3.

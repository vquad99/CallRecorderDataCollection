# Exotel - what the official documentation says (read 2026-11-10)

Chosen by the owner on 2026-11-10 (Indian provider, quickest to onboard). The adapter is written
only from the pages listed here (GEN-005). Nothing below has been tested on a real account yet;
NOT DOCUMENTED / CONFLICT marks what the proof of capability (Gate 5) must settle.

## Calls used

- **Connect two numbers**: `POST https://<host>/v1/Accounts/<sid>/Calls/connect.json`, HTTP Basic
  (API key : API token), form-encoded. Host `api.in.exotel.com` (Mumbai) or `api.exotel.com`
  (Singapore); the region is fixed per account. `From` is called first, then `To`; `CallerId` is
  the ExoPhone. Options used: `Record=true`, `RecordingChannels=dual`, `RecordingFormat=mp3-hq`
  (needs enabling by Exotel; default `mp3`), `TimeLimit` (max 14400 s), `TimeOut`,
  `StatusCallback`, `StatusCallbackEvents` (`terminal`, `answered`),
  `StatusCallbackContentType=application/json`, `CustomField` (max 128 characters),
  `CallType=trans`.
- **Answer**: `{"Call": {"Sid", "Status", "DateCreated", "RecordingUrl", ...}}`. Status values:
  queued, ringing, in-progress, completed, failed, busy, no-answer, canceled. Errors:
  `{"RestException": {"Status", "Message"}}`; 429 above 200 requests a minute; 402 no balance.
- **Status callback**: POST to our URL with `CallSid`, `Status`, `RecordingUrl`, `EventType`,
  `ConversationDuration`, `StartTime`, `EndTime`, `CustomField`, `Legs[]` (`Status`,
  `OnCallDuration`). Must answer 200 within 15 s; retried up to 2 times.
- **Call details**: `GET .../Calls/<CallSid>.json?details=true` (same fields, plus per-leg status).

## What limits the design

| Topic | Documentation says | Consequence |
|---|---|---|
| Separate speakers | `RecordingChannels=dual` for a two-party call; "Left: first party; Right: second party" (generic wording) | A and B alone on the recorded call; the moderator takes consent on separate calls first. Channel order must be proven by a test call. |
| Recording format | MP3 only by API (`mp3`, `mp3-hq`): stereo 12 kbps per channel, or 32 kbps per channel with HQ. WAV by API NOT DOCUMENTED. Sample rate NOT DOCUMENTED. | The provider original is a lossy MP3. The delivery WAV is that MP3 decoded: 8 kHz phone audio, up-sampled, with MP3 loss. Must be told to the client (B-02) and stated in the file's history. |
| Callback authenticity | No signature. Only "verify source IP ranges; contact support for the list". | Callback URL carries a per-call secret; every callback is confirmed against the Call details API before it changes anything. |
| Do-not-disturb numbers | A number on the DND registry can be called only if it "has called on your ExoPhone at least once in the past 6 months", or after a DND enablement with opt-in proof. | Participants on DND give a missed call to the ExoPhone first, or the owner files the opt-in declaration. |
| Recording download | CONFLICT: plain URL, or API credentials, or a pre-signed URL (5-60 min) on secure-recording accounts. Ready 1-5 minutes after the call (up to 15). | Try in that order; poll until ready. |
| Retention at Exotel | CONFLICT: 30, 90 or 180 days by plan. Delete by API NOT DOCUMENTED. | Copy to our storage at once; deletion at Exotel is a support request. |
| Capacity | 60 outbound calls a minute by default; concurrency 10 / 30 / custom by plan; rate limit 200 requests a minute | 50 conversations at once need an Enterprise plan (sales). |
| Trial | 7 days, one ExoPhone, calls only to 10 OTP-verified numbers, recording available | Enough for Gate 5. KYC (1-3 working days) before going live. |
| Consent announcement | Not enforced; recommended. `StartPlaybackToNew=Both` + `StartPlaybackValueNew` plays audio before the call connects. | An announcement file can be played to both parties at the start. |
| Conference (Legs API) | Events over gRPC only; recording per leg NOT DOCUMENTED | Not used. |

## Sources

developer.exotel.com/docs: voice-v1/api-reference/connect-two-numbers, status-callback,
call-details; references/authentication, error-codes, webhooks; reporting/recording-access;
getting-started/regions-availability, trial-account, kyc-verification; faqs/voice-faqs,
calling-hours, spam-prevention; legs/overview. docs.exotel.com/business-phone-system:
call-recordings, secure-call-recording, calling-whitelisted-customer, enable-dnd-calling.

# Telephony provider evaluation

Status: NOT STARTED. No provider has been researched, contacted or tested in this project.
Every cell below is **NOT VERIFIED** until it carries an official documentation URL with access date
(saved under docs/integrations/<provider>/) or a written provider answer, plus test evidence where the
item is testable (TEL-021, TEL-022, GEN-005).

At least two providers must be evaluated. A cheap advertised plan or a marketing page is not evidence.

## Candidates

None selected. Earlier informal conversation outside this project mentioned Exotel, TeleCMI, Ozonetel,
Jio Business and Tata Tele Business Services; none of their claims has been checked here and none is
assumed. The owner chooses the shortlist (DECISIONS.md B-01).

## Criteria (runbook H1)

| # | Criterion | Why it matters | Provider 1 | Provider 2 |
|---|---|---|---|---|
| 1 | India outbound calling | participants on Indian numbers | NOT VERIFIED | NOT VERIFIED |
| 2 | API call creation | start call to A from the portal | NOT VERIFIED | NOT VERIFIED |
| 3 | Conference creation | A, B, moderator in one bridge | NOT VERIFIED | NOT VERIFIED |
| 4 | Add participant to an active conference | add B after A answers | NOT VERIFIED | NOT VERIFIED |
| 5 | Moderator departure without ending the conference | core workflow | NOT VERIFIED | NOT VERIFIED |
| 6 | Recording continues after moderator leaves | core workflow | NOT VERIFIED | NOT VERIFIED |
| 7 | Separate participant tracks or verified dual-channel | stereo A/B requirement | NOT VERIFIED | NOT VERIFIED |
| 8 | Recording retrieval API | automated download | NOT VERIFIED | NOT VERIFIED |
| 9 | Webhooks and signatures | events, security | NOT VERIFIED | NOT VERIFIED |
| 10 | 50 concurrent conferences (written) | capacity | NOT VERIFIED | NOT VERIFIED |
| 11 | Call-leg limits (100 or 150 legs) | capacity | NOT VERIFIED | NOT VERIFIED |
| 12 | Recording format and sample rate (codec, 8 or 16 kHz) | 16 kHz requirement (B-02) | NOT VERIFIED | NOT VERIFIED |
| 13 | Retention and storage of recordings at the provider | privacy | NOT VERIFIED | NOT VERIFIED |
| 14 | Per-minute cost and fixed charges (written quote) | budget | NOT VERIFIED | NOT VERIFIED |
| 15 | Contract, compliance, recording-consent requirements | legal (B-10) | NOT VERIFIED | NOT VERIFIED |
| 16 | Browser (WebRTC) client for the moderator | leg count (D-008) | NOT VERIFIED | NOT VERIFIED |
| 17 | Data hosting location | data residency (B-04) | NOT VERIFIED | NOT VERIFIED |
| 18 | Enterprise plan required for any item above | cost | NOT VERIFIED | NOT VERIFIED |

## Proof of capability (Phase 5, runbook H2-H4)

Run only with test credentials stored server-side, in an isolated proof-of-concept. Evidence goes to
docs/evidence/phase5/ (call IDs, provider event IDs, files, ffprobe output, listening notes). The
provider is accepted only when every critical item (3-12) has evidence. Otherwise telephony stays
BLOCKED and alternatives are presented.

## Result

No result. Telephony requirements TEL-001..038 are BLOCKED (BUILD_STATUS.md).

## Desk research, 2026-11-10 (official pages only; nothing tested yet)

Twelve providers were read against the telephony flow (call A, add B, moderator joins and leaves,
record, fetch) on 2026-11-10. Every claim below is from the provider's own documentation or pricing
page on that date; NOT VERIFIED = not found on an official page. No account was opened and no call
was placed, so nothing here is proven (GEN-005): Gate 5 still needs a working test.

Findings that hold for every provider:

- Phone-network audio is narrowband 8 kHz (G.711). A 16 kHz telephony WAV is an up-sample (B-02).
- No provider documents a ready "A left, B right" file for a three-party conference. Each
  participant's leg is recorded separately and the stereo file is built by this platform.

| Provider | Conference by API; moderator can leave | Each speaker separately | Legal India-to-India, Indian caller ID | Signed webhooks | Self-serve trial | Published cost, 30-min conversation |
|---|---|---|---|---|---|---|
| Plivo | Yes (`end_mpc_on_exit` false) | Participant-level recording; isolation and sample rate NOT VERIFIED | Yes: India-registered business, KYC, Plivo Indian number; no browser leg in a phone conference | HMAC-SHA256 | NOT VERIFIED | about Rs 24 (Rs 0.38/min) |
| Telnyx | Yes | Per-leg recording; rate NOT VERIFIED | Yes since 2026-09-17, four districts; caller-ID rules not stated | Ed25519 | Yes | India rate not published |
| Vonage | Yes | Yes, one channel per leg, 16 kHz 16-bit WAV | No: foreign caller ID advised | JWT | NOT VERIFIED | NOT VERIFIED |
| Twilio | Yes | Per-leg mono files | No: "only from international (non-Indian) numbers" | HMAC-SHA1 | Yes | about USD 3.25 |
| Infobip | Yes | One WAV per participant; rate NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | Yes | India rate not published |
| Sinch | Yes; moderator leaving NOT VERIFIED | No (mix only) | NOT VERIFIED | HMAC-SHA256 | Yes | NOT VERIFIED |
| Exotel | Partial (Legs API; mute / leave NOT VERIFIED) | Dual-channel for a two-party call only | Yes after KYC; recordings stored in India | Not documented | Yes (7 days) | per-minute rate not published |
| Ozonetel KOOKOO | Yes (room continues when one leaves) | No (one mixed 8 kHz MP3) | Yes on a paid account; 50 calls/day until raised | Not documented | Yes | NOT VERIFIED |
| Knowlarity | No conference API | No | Yes | Not documented | Unclear | about Rs 25-38 |
| Tata Smartflo / Kaleyra | No conference API | No | Yes | Not documented | No (sales) | NOT VERIFIED |
| Airtel IQ | NOT VERIFIED (no public API reference) | NOT VERIFIED | Yes | NOT VERIFIED | No (sales) | NOT VERIFIED |
| MyOperator | No conference API | No | Yes | Basic / API-key auth | Plan-gated | inside the plan |

Shortlist for a proof of capability (Gate 5): **Plivo** first (only documented, priced, compliant
domestic route with a full conference API and signed webhooks), **Exotel** second (Indian storage
and a trial, but separate speakers are documented for two-party calls only). What the proof must
show for Plivo: that participant-level recording holds one speaker only, its real sample rate and
format, that the conference survives the moderator hanging up, and the concurrency an Enterprise
plan gives (default 50 legs; 50 conferences need 100 to 150).

Sources: plivo.com/docs (multiparty-calls, india-calling, india-concurrency, signature-validation),
plivo.com/voice/pricing/in; twilio.com/en-us/guidelines/in/voice, twilio.com/docs/voice/api;
developer.vonage.com (recording, ncco-reference); developers.telnyx.com, telnyx.com/release-notes/
india-mobile-numbers; developers.sinch.com/docs/voice; infobip.com/docs/voice-and-video;
developer.exotel.com (legs, call-recording, regions); cpaas.ozonetel.com; developer.knowlarity.com;
docs.smartflo.tatatelebusiness.com; airtel.in/business/b2b/voice-api; myoperator.com/pricing.

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

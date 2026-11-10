# Kathbath / AI4Bharat collection practice - what we could adopt

Researched 2026-11-10 from primary sources (all accessed 2026-11-10). Nothing here is built yet;
each item needs the owner's choice. Items not confirmed in a source are marked NOT VERIFIED.

## How Kathbath was collected

- Collected on Microsoft's open-source **Karya** Android app (IndicSUPERB paper, section 3; the
  Hugging Face card thanks Karya Inc.). https://arxiv.org/abs/2208.11761 ,
  https://huggingface.co/datasets/ai4bharat/Kathbath
- **Read speech**, not conversation: IndicCorp sentences of 8-15 words, in batches of 100; one access
  code per batch; consent explained by a local coordinator and shown in the app before recording.
- 1,218 speakers, 203 districts, 22 states, about 50/50 gender. Released fields: `fname, text,
  audio_filepath, lang, duration, gender, speaker_id` (m4a).
- One human verifier per recording; three 0-2 scores; rejected-but-usable audio kept as a separate
  "noisy" set.
- AI4Bharat's later **IndicVoices** (also on Karya) recorded two-person conversations over a phone
  bridge - our telephony mode - with a 23-reason rejection list, age / education / district quotas
  and identity checks. https://arxiv.org/abs/2403.01926
- Karya code: 44.1 kHz mono 16-bit PCM encoded to m4a, 250 ms kept before and after each take,
  listen-back before "Next", file checksums, offline field server.
  https://github.com/microsoft/rural-crowdsourcing-toolkit
- Not confirmed for Kathbath: automatic silence / SNR / clipping checks, more than one reviewer,
  speaker identity checks, dashboards, devices used (NOT VERIFIED).

## Candidates for this platform (ranked)

| # | Feature | Why | Source | Effort |
|---|---|---|---|---|
| 1 | QC scores (content, volume, noise 0-2) with a "noisy" tier instead of plain pass/fail | Consistent decisions; usable audio kept | Kathbath s.3/4.1 | S |
| 2 | Fixed rejection-reason list (IndicVoices' 23: single speaker, chatter, echo, wrong language, off topic, long pauses, wrong metadata...) | Countable reasons, moderator coaching | IndicVoices Table 12 | S |
| 3 | Speaker demographics (age band, gender, district, education) and a balance / quota view on the dashboard | Clients see balance, not just hours | Kathbath s.3; IndicVoices | M |
| 4 | Moderator quick check after each session (audible / both speakers / long enough) | Catches bad sessions before central QC | IndicVoices s.4.4/5 | S |
| 5 | Conversation scenario prompts (general, state, district) assigned per task | Topic variety, less repetition | IndicVoices s.3.7 | S-M |
| 6 | Duplicate-speaker flag at QC (same person under several IDs) | Speaker-disjoint data | IndicVoices s.5 | M |
| 7 | Automatic pre-QC flags (one channel near silent, Deepgram reports another language, low confidence) | QC time goes to doubtful files | Karya `SpeechVerification.ts`; LREC 2020 | M |
| 8 | Minutes-per-participant target and counter | Plan for rejections (target 25-35 min for 20 usable) | IndicVoices s.4.2/4.4 | S |
| 9 | Second-level QC on a sample (K %) with a 3-return limit | Checks the checkers | Shoonya `k_value`, `revision_loop_count` | M |
| 10 | Payment ledger tied to QC results | If participants are paid per accepted hour | Karya `SpeechValidation.ts` | M |
| 11 | Delivery manifest with speaker IDs and held-out speakers | Speaker-disjoint test sets | HF card; Kathbath s.4.1 | S |
| 12 | 250 ms padding around takes, listen-back before submit, local buffering | Field robustness | Karya app code | M-L |

Items 1, 2, 4 and 7 fit Phase 7 (audio QC); 3, 8 and 11 fit Phases 7 and 9.

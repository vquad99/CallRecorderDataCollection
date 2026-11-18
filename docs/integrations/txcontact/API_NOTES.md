# TxContact (Telenetix) - what we were given and what the API description says (read 2026-11-13)

Offered by DesiCrew / Telenetix by email on 2026-11-13 and chosen by the owner the same day
(D-101). The adapter (`backend/app/adapters/txcontact.py`) uses only the two sources below
(GEN-005). **Nothing here has been tested on the TxContact account yet.** Items marked NOT
VERIFIED must be settled by the first real call.

## Sources

1. **Dialer**: TxContact's email of 2026-11-13, one example request (credentials not copied here):
   `GET https://amber.txcontact.com/txdialer/api/contact/add?username=…&password=…&cmp-ref=dc-record-call&phone=<10 digits>&preferred-agent=<agent id>&source=webapi`
2. **Recording service**: the published API description
   `https://amber.txcontact.com/txrecord/swagger.json` (Swagger 2.0, "TxRecord API" v1, generated
   by drf-yasg). The page `/txrecord/swagger/` is only the viewer for it.

## Tested on the account, 2026-11-13

No phone was rung: the dialer was only sent the invalid number `0000000000`.

| Test | Result | What it settles |
|---|---|---|
| Dialer, real login, number `0000000000` | HTTP 200, `text/html`, body a UUID (e.g. `fec72ece-df50-11f1-96b6-bc24110b2437`) | An accepted request returns an identifier. The platform stores it as `calls.provider_reference` (migration 0019). Which recording field carries it is still NOT VERIFIED. |
| Dialer, wrong password | HTTP 200, `text/html`, **empty body** | A wrong login is not an HTTP error. The platform treats an empty answer as refused ("usually a wrong dialer username or password"). |
| Recording sign-in (`/auth/`, `/getjwt/`, `/base64token/`) with the dialer login | HTTP 400 `{"status": "ERROR", "message": "invalid username/password"}`; once, a 500 with a MySQL error on TxContact's side | The recording service needs **its own login**: ask TxContact for it. The search, time zone, number format and recording format cannot be tested until then. |

## Tested on the account, 2026-11-15 (read only; no phone was rung)

TxContact sent new details: campaigns `dc-new-call` (ring A) and `dc-attach-call` (ring a number
into the call on the seat), a test agent seat, and a token for the recording service.

| Test | Result | What it settles |
|---|---|---|
| Recording search with `Authorization: Basic <token>` | 200 JSON `{count, next, previous, results}`; without the header 403 | The recording service takes the record login itself (the token is base64 of user:password). No sign-in request is needed |
| Search of 13-14 Nov, any seat | 21 records of earlier test calls made by TxContact's staff on seats 80001, 80002 | The fields are filled as below |
| Download of one earlier recording | 200 `audio/x-wav`, Content-Length given; RIFF WAV, PCM, 1 channel, 8000 Hz, 16-bit (deleted after the check) | The download works; the file is one channel, so the speakers are mixed |

What the records show (numbers not copied here): times carry the zone (`+05:30`); `sl_rec_filename`
holds the tenant, the agent's name and seat, numbers, the queue and the session id, and the
download takes it with `.` and `sl_rec_filename_ext` (`mp3` earlier, `wav` later);
`sl_rec_status` is `D` or `E`; every `sl_ref_field1..20` is empty. Each test call appears as two
records: one in queue `Outbound` (from a short extension to the participant's number, a session
id different from the transaction id) and one in the campaign's queue (`dcrecordcall`) where
`sl_from` and `sl_to` both hold the participant's number. The id the dialer returns (a
time-based UUID) is not the session id (random UUIDs): a call cannot be found by it.

## Calls used

| Purpose | Request | Notes |
|---|---|---|
| Ring participant A, connect to the moderator's seat | `GET /txdialer/api/contact/add` with `username`, `password`, `cmp-ref`, `phone`, `preferred-agent`, `source` | Credentials travel in the address (TxContact's design). The platform never logs the address. The answer format is NOT VERIFIED: HTTP 2xx without words like "error"/"invalid"/"fail" counts as accepted, and the shortened answer (credentials and number removed) is kept in the call's history. |
| Sign in to the recording service | `POST /txrecord/api/v1/auth/` with JSON `{user_id, password}` → `{status, auth_token}` | 400 = wrong user or password; 404 = inactive user. |
| Find the call | `GET /txrecord/api/search?sl_agent_id=<seat>&sl_start_date=YYYY-MM-DD&page=N` → `{count, next, previous, results: [Sessionlog]}` | One day per search, no date range. Fields used: `sl_session_id`, `sl_trans_id`, `sl_from`, `sl_to`, `sl_agent_id`, `sl_start_time`, `sl_end_time`, `sl_rec_filename`, `sl_rec_filename_ext`, `sl_rec_file_duration`, `sl_rec_status`. |
| Download the recording | `GET /txrecord/download/{filename}` | Response format not described. |

Authentication for the recording service is an API key in the `Authorization` header. The
description does not say the word before the token (`Token`, `Bearer`, `JWT` or none): NOT
VERIFIED, set by `TXCONTACT_AUTH_SCHEME` (default `Token`, the Django REST framework default).

## What limits the design

| Topic | What we know | Consequence |
|---|---|---|
| Adding participant B | TxContact's email of 2026-11-15: the same dialer request with `cmp-ref=dc-attach-call` rings a number into the call on that seat (A is rung with `dc-new-call`). | The moderator clicks **Call participant B** once A is on the line (D-111). NOT VERIFIED until one real call: that B joins the call already on the seat, and how its recording is listed. |
| Moderator leaving | Not described. | Whether A and B stay connected and recorded after the moderator leaves is NOT VERIFIED. |
| Linking our call to TxContact's | The dial answer gives no call ID (NOT VERIFIED); the dialer takes no reference of ours. | The platform finds the call by agent seat, time (dial to close, ±2 min) and A's number in `sl_from`/`sl_to`. If several fit, or the number is not shown, a person picks the call. |
| Callbacks | None in the description. | The platform asks every minute or so after the call is closed (backing off to 5 minutes), for `TELEPHONY_FETCH_MINUTES` (default 60), then asks a person. |
| Recording format | Not described; examples mention `.wav` and `.mp4`. | Read with libsndfile (WAV incl. µ-law/A-law, MP3, FLAC, Ogg). MP4/AAC cannot be read: the call shows "Recording could not be fetched" with the reason. Sample rate and channels are recorded as found. |
| Separate speakers | Not described. | The provider file is kept unchanged; the 16 kHz delivery file keeps every channel the provider sends, never mixed. A one-channel file holds everyone, including the moderator (no A-left/B-right file). |
| Time zone | `sl_start_time` is "date-time" without a stated zone. Seen 2026-11-17: a call placed at 14:52:03 IST was listed as `2026-11-17T20:22:07+05:30`, 5 h 30 min ahead, and filed under the date of that time. | Times without a zone are read as `TXCONTACT_TIMEZONE` (default Asia/Kolkata). Every time is then moved back by `TXCONTACT_CLOCK_AHEAD_MINUTES` (`330` on the live site), and the dates searched are moved forward by it (D-131). |
| Number format | The example dials 10 digits with no country code. | Only Indian mobile numbers (+91, 10 digits from 6-9) are dialled; others are refused before calling. |
| Limits, cost, data location, retention | Not described. | Ask TxContact (see questions below). |

## How the platform behaves around these limits (D-103)

- The moderator confirms on a checklist that A and B joined; the platform cannot see it.
- The moderator stays on the call, muted, and cancels with "Poor line quality" when needed.
- A call can be cancelled at every stage. A search that keeps failing (for example the recording
  login refused, as on 2026-11-13) ends with a person after the fetch window.
- After a redial on the same seat within two minutes, only calls that started from 10 s before
  the redial are considered, so a dropped first attempt is not taken for the second.
- A download is checked against the length TxContact announces; redirects are refused.
- TxContact's call ids and file names are shown masked: they may carry the caller's number.
- At most 6 calls an hour for a task; a participant who refused consent is not called again.
- A stand-in that answers like the real service (as seen and documented above) is in
  `backend/tests/fake_txcontact.py`; the browser journey `frontend/journeys/phonecall.spec.ts`
  runs the whole flow against it (locally, and in CI once the journeys job starts the stand-in;
  without a configured provider the journey is skipped).

## Questions sent / to send to TxContact

1. What does `contact/add` answer on success and on failure? Does it return a call ID?
2. Can the agent add B as a conference and leave, with A and B still connected and recorded?
3. Recording format: codec, sample rate, channels; can A and B be on separate channels?
4. Which word goes before the token in the `Authorization` header?
5. Time zone of `sl_start_time`; do `sl_from`/`sl_to` hold the customer's number?
6. Can the dialer carry a reference of ours (one of `sl_ref_field1..20`)?
7. Concurrent calls (we need 50), price per minute, where recordings are stored and for how long.
8. Separate test credentials, and a way to send the dialer password other than in the address.

## Configuration

`TXCONTACT_BASE_URL`, `TXCONTACT_DIALER_USERNAME`, `TXCONTACT_DIALER_PASSWORD`,
`TXCONTACT_CAMPAIGN_REF` (default `dc-record-call`), `TXCONTACT_SOURCE` (default `webapi`),
`TXCONTACT_RECORD_USER`, `TXCONTACT_RECORD_PASSWORD`, `TXCONTACT_AUTH_SCHEME`,
`TXCONTACT_TIMEZONE`, `TXCONTACT_CLOCK_AHEAD_MINUTES` (D-131), `TELEPHONY_FETCH_MINUTES`. Each
moderator's seat number and seat password (D-130) are set on their user page (**Phone calls →
Seat number, Seat password**).

The dialer password that came in the email was shared with several people in plain text. Ask
TxContact to change it after the first test, and enter the new one only in Render.

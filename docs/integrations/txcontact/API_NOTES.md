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
3. **Agent manager** (the seat's sign-in, D-133): TxContact's "TxAgentManager - API Specification
   Document" 1.18.0-0, a PDF given on 2026-11-18. See "The moderator's seat" below.

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
| Recording format | Not described; examples mention `.wav` and `.mp4`. TxContact stated (2026-11-18): WAV, stereo, 16 kHz; a real phone task's recording then measured 2 channels. Earlier test calls (2026-11-15) were 1 channel, 8 kHz. | Read with libsndfile (WAV incl. µ-law/A-law, MP3, FLAC, Ogg). MP4/AAC cannot be read: the call shows "Recording could not be fetched" with the reason. Sample rate and channels are recorded as found. A project's phone rule expects 16 kHz, 16-bit, stereo (D-134); a 16 kHz file is copied into the delivery file sample for sample, another rate is resampled to 16 kHz. |
| Separate speakers | Stereo, but which voice is on which channel is NOT VERIFIED. A contact centre often records the agent on one channel and everyone else on the other; then A and B share a channel and the muted moderator's channel is nearly silent. | The provider file is kept unchanged; the 16 kHz delivery file keeps both channels, never mixed. A one-channel file fails the automatic check with "A track is missing" (MISSING_TRACK), so a change at TxContact is caught. Settle the channel layout with the first real call (left alone, right alone). |
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
- A stand-in that answers like the real service (as seen and documented above, the agent
  manager included) is in `backend/tests/fake_txcontact.py`; the browser journey
  `frontend/journeys/phonecall.spec.ts`
  runs the whole flow against it (locally, and in CI once the journeys job starts the stand-in;
  without a configured provider the journey is skipped).

## The moderator's seat: TxContact's agent manager (D-133)

Source 3: TxContact's "TxAgentManager - API Specification Document", version 1.18.0-0 (dated
31-05-2022), given by TxContact on 2026-11-18 (a PDF; not copied here). It is how the Chirp app
signs a seat in. The portal now does the same from the moderator's browser, so the Chirp app is
not needed: the dialer connects participant A to the seat only while the seat is Ready.

Seen on 2026-11-18 before any code was written (a connection opened, nothing sent): the address
`wss://amber.txcontact.com/txagentmanager/` is a plain WebSocket (not Socket.IO) and says nothing
until the client speaks. The Chirp app's log shows TxContact closing the connection every 5
minutes and Chirp connecting again 2 seconds later with RECONNECT and the same session. Tenant:
`desicrew`. States named in the document: `OFFLINE`, `ONBREAK`, `READY_FOR_CALL`.

| Sent by the portal | When |
|---|---|
| `CONNECT` `{EVENT_NAME, EVENT_CLASS: "AGENT", PLUGINS: ["PHONE", "CHAT", "BROWSER"], AUTH: {AGENT_ID, TENANT_ID, PASSWORD}}` | When a moderator with a saved seat password opens the portal |
| `LOGIN` `{EVENT_NAME, EVENT_CLASS, SESSION_ID, DATA: {EXTENSION}}` (the optional `URI` is not sent) | After the first `CONNECTED` |
| `CHANGE_AGENT_STATE` `{..., DATA: {STATE, EXTENSION}}` | `READY_FOR_CALL` after TxContact's answer to `LOGIN` (or 2 s without one); again when a call is closed or cancelled in the portal, and after any other state while no call is open (3 asks at most); `OFFLINE` at sign-out |
| `LOGOUT` `{..., DATA: {EXTENSION}}`, then `DISCONNECT` `{..., DATA: {}}` | At portal sign-out, also the idle sign-out |
| `RECONNECT` `{EVENT_NAME, EVENT_CLASS, SESSION_ID, PLUGINS, AUTH}` | 2 s after TxContact closes the connection; 3 tries |

| Sent by TxContact | What the portal does |
|---|---|
| `CONNECTED` `{SESSION_ID}` | Keeps the session; sends `LOGIN` the first time |
| `AGENT_STATE_CHANGED` `{DATA: {AGENT_ID, TENANT_ID, STATE, STATE_DESC, STATE_CHANGE_TIME}}` | Shows the state in the top bar; `READY_FOR_CALL` ends the sign-in. Another seat's change is ignored |
| `ALERT` `{DATA: {MESSAGE}}` | Before Ready: the sign-in failed and `MESSAGE` is the reason shown. Later: kept as the reason if the connection is then lost |
| `DISCONNECTED` | Before Ready: the sign-in failed. Later: connect again (`RECONNECT`) |
| `NOTIFY`, `ROSTER`, `AGENT_STATE_BROADCAST`, anything else | Kept in the Super Admin's phone line log only |

Answers are read whatever the case of their keys. Every frame sent and received is kept in the
page's memory for the Super Admin (**Phone line log (this browser)** on a phone task); the password
is never in it, nor in browser storage.

NOT VERIFIED until the first live test, and what to change if the guess is wrong:

| Unknown | Assumed | If wrong |
|---|---|---|
| The exact key format | Upper-case keys, as the document writes them | A code change in `frontend/src/features/phoneline/seatLink.ts` |
| The `EXTENSION` of a seat | The seat number itself | `TXCONTACT_EXTENSION`: `{seat}` stands for the seat number (for example `9{seat}`), or a fixed value |
| Tenant | `desicrew` | `TXCONTACT_TENANT_ID` |
| Address | `wss://amber.txcontact.com/txagentmanager/` | `TXCONTACT_AGENT_URL`, and `connect-src` in `frontend/nginx.conf` for another host |
| A browser's connection (its Origin) accepted | Yes | The top bar says "Phone line not connected: TxContact could not be reached". Ask TxContact to allow the site's address; meanwhile `TXCONTACT_SEAT_LOGIN=false` and the Chirp app |
| TxContact's answer to `LOGIN` | A state change, or nothing | Nothing to change: Ready is asked 2 s after `LOGIN` at the latest |
| States during and after a call | Anything but `READY_FOR_CALL` | Nothing to change: left alone while the call is open, Ready asked once it is closed |
| Whether `LOGOUT` drops a call still on the seat | Not tested | The portal signs out only at portal sign-out; avoid signing out during a call |
| Whether a reload's fresh `CONNECT` is refused while the old session is alive | Not refused | The top bar shows TxContact's reason; **Try again** a little later |
| Two tabs of one moderator (each signs the seat in) | TxContact allows it, or ends the older session | An ended session's `RECONNECT` fails 3 times, then that tab says "not connected" and does not take the seat back by itself. If tabs fight, make calls from one tab only |

## Questions sent / to send to TxContact

1. What does `contact/add` answer on success and on failure? Does it return a call ID?
2. Can the agent add B as a conference and leave, with A and B still connected and recorded?
3. Recording format: answered 2026-11-18, WAV, stereo, 16 kHz. Still open: who is on which
   channel (agent, A, B), and can A and B be on separate channels?
4. Which word goes before the token in the `Authorization` header?
5. Time zone of `sl_start_time`; do `sl_from`/`sl_to` hold the customer's number?
6. Can the dialer carry a reference of ours (one of `sl_ref_field1..20`)?
7. Concurrent calls (we need 50), price per minute, where recordings are stored and for how long.
8. Separate test credentials, and a way to send the dialer password other than in the address.

## Configuration

`TXCONTACT_BASE_URL`, `TXCONTACT_DIALER_USERNAME`, `TXCONTACT_DIALER_PASSWORD`,
`TXCONTACT_CAMPAIGN_REF` (default `dc-record-call`), `TXCONTACT_SOURCE` (default `webapi`),
`TXCONTACT_RECORD_USER`, `TXCONTACT_RECORD_PASSWORD`, `TXCONTACT_AUTH_SCHEME`,
`TXCONTACT_TIMEZONE`, `TXCONTACT_CLOCK_AHEAD_MINUTES` (D-131), `TELEPHONY_FETCH_MINUTES`; for the
seat sign-in (D-133) `TXCONTACT_AGENT_URL` (empty: `TXCONTACT_BASE_URL` with wss:// and
/txagentmanager/), `TXCONTACT_TENANT_ID` (`desicrew`), `TXCONTACT_EXTENSION` (empty: the seat
number) and `TXCONTACT_SEAT_LOGIN` (on; off: the Chirp app). Each moderator's seat number and
seat password (D-130) are set on their user page (**Phone calls → Seat number, Seat password**).

The dialer password that came in the email was shared with several people in plain text. Ask
TxContact to change it after the first test, and enter the new one only in Render.

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
| Adding participant B | The dialer rings one number and connects it to an agent seat. No API to add a second number or make a conference. | The moderator is the TxContact agent and adds B from the TxContact agent screen (owner, D-101). The platform cannot see or control that step. |
| Moderator leaving | Not described. | Whether A and B stay connected and recorded after the moderator leaves is NOT VERIFIED. |
| Linking our call to TxContact's | The dial answer gives no call ID (NOT VERIFIED); the dialer takes no reference of ours. | The platform finds the call by agent seat, time (dial to close, ±2 min) and A's number in `sl_from`/`sl_to`. If several fit, or the number is not shown, a person picks the call. |
| Callbacks | None in the description. | The platform asks every minute or so after the call is closed (backing off to 5 minutes), for `TELEPHONY_FETCH_MINUTES` (default 60), then asks a person. |
| Recording format | Not described; examples mention `.wav` and `.mp4`. | Read with libsndfile (WAV incl. µ-law/A-law, MP3, FLAC, Ogg). MP4/AAC cannot be read: the call shows "Recording could not be fetched" with the reason. Sample rate and channels are recorded as found. |
| Separate speakers | Not described. | The provider file is kept unchanged; the 16 kHz delivery file keeps every channel the provider sends, never mixed. A one-channel file holds everyone, including the moderator (no A-left/B-right file). |
| Time zone | `sl_start_time` is "date-time" without a stated zone. | Times without a zone are read as `TXCONTACT_TIMEZONE` (default Asia/Kolkata): NOT VERIFIED. |
| Number format | The example dials 10 digits with no country code. | Only Indian mobile numbers (+91, 10 digits from 6-9) are dialled; others are refused before calling. |
| Limits, cost, data location, retention | Not described. | Ask TxContact (see questions below). |

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
`TXCONTACT_TIMEZONE`, `TELEPHONY_FETCH_MINUTES`. Each moderator's agent seat is set on their user
page (**Phone calls → TxContact agent seat**).

The dialer password that came in the email was shared with several people in plain text. Ask
TxContact to change it after the first test, and enter the new one only in Render.

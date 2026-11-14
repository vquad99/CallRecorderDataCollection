# User journeys

Real browser, real backend, real database and file storage; nothing is mocked, except the phone
provider in `phonecall.spec.ts` (a call cannot be placed from a test). Each journey uses
its own project and user names, so runs never collide and no clean-up is needed between runs.

| File                  | Journey                                                                                                                                                                                                                                                                                                                                                                                                              |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `recording.spec.ts`   | Super Admin creates a project, invites a moderator by email; the moderator sets a password, starts the task, records consent and a face-to-face conversation, plays it back; the files download intact through short-lived links; the audit log shows the steps                                                                                                                                                      |
| `interrupted.spec.ts` | The tab closes mid-recording; on return the moderator is told how much was kept, keeps it, and the task is recorded                                                                                                                                                                                                                                                                                                  |
| `boundaries.spec.ts`  | Moderator, QC executive and client viewer try pages and records that are not theirs, by menu and by typed address; signing out and going back shows sign-in                                                                                                                                                                                                                                                          |
| `password.spec.ts`    | A forgotten password is reset from the email; the old password stops working and the other device's session ends                                                                                                                                                                                                                                                                                                     |
| `network.spec.ts`     | The connection drops for 8 s mid-recording; the page keeps capturing, says parts are waiting, sends them when the connection returns; nothing is lost                                                                                                                                                                                                                                                                |
| `session.spec.ts`     | An administrator ends the moderator's sessions mid-recording; the page asks for a new sign-in, capture goes on, and after signing in again in another tab the waiting parts are sent; nothing is lost                                                                                                                                                                                                                |
| `dashboard.spec.ts`   | Client viewer, moderator and administrator each land on their own dashboard view; the period filter changes the request; two-step sign-in refuses to start with a wrong password                                                                                                                                                                                                                                     |
| `participant.spec.ts` | Staff write the consent form and create a personal link; the participant opens it without an account, sees only their own session, agrees, withdraws; staff see the answers; a new link ends the old one                                                                                                                                                                                                             |
| `phonecall.spec.ts`   | The Super Admin gives a moderator an agent seat; a refused dial is shown as refused; the moderator calls, ticks the checklist, records consent, closes the call; the recording arrives by itself, plays, passes the automatic check and goes to QC; the Phone calls page counts it and the details file tells the call's story. The phone provider is a stand-in (`backend/tests/fake_txcontact.py`): no phone rings |
| `twostep.spec.ts`     | An admin signs in with the password and gets only the set-up page; sets up two-step sign-in with a real code; signs in again with password and code; turns it off and is back at the set-up. Runs only with `E2E_ADMIN_MFA=1` against a backend started with `REQUIRE_ADMIN_MFA=true` (CI's backend has the rule off and skips it)                                                                                   |

## Run locally

1. Backend on port 8000 with a database and storage configured, `EMAIL_BACKEND=file`,
   `EMAIL_FILE_DIR=<dir>`, `PUBLIC_APP_URL=http://127.0.0.1:5181`, then
   `python -m app.cli seed-dev` (needs `DEMO_PASSWORD`). For the phone-call journey also start
   `python -m tests.fake_txcontact 8765` in `backend/` and give the backend
   `TXCONTACT_BASE_URL=http://127.0.0.1:8765`, `TXCONTACT_DIALER_USERNAME=fake_dialer`,
   `TXCONTACT_DIALER_PASSWORD=fake-dialer-pass`, `TXCONTACT_RECORD_USER=fake_rec`,
   `TXCONTACT_RECORD_PASSWORD=fake-rec-pass`, `TELEPHONY_FIRST_LOOK_SECONDS=1`,
   `RECOVERY_INTERVAL_SECONDS=2` (without them that journey is skipped).
2. `E2E_ADMIN_PASSWORD=<DEMO_PASSWORD> E2E_OUTBOX=<dir> make journeys`
   (`PW_CHANNEL=chrome` uses an installed Google Chrome; `PW_EDGE=1` adds Microsoft Edge).

CI runs the same against PostgreSQL and SeaweedFS (job "User journeys in a real browser").

# User journeys

Real browser, real backend, real database and file storage; nothing is mocked. Each journey uses
its own project and user names, so runs never collide and no clean-up is needed between runs.

| File                  | Journey                                                                                                                                                                                                                                                         |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `recording.spec.ts`   | Super Admin creates a project, invites a moderator by email; the moderator sets a password, starts the task, records consent and a face-to-face conversation, plays it back; the files download intact through short-lived links; the audit log shows the steps |
| `interrupted.spec.ts` | The tab closes mid-recording; on return the moderator is told how much was kept, keeps it, and the task is recorded                                                                                                                                             |
| `boundaries.spec.ts`  | Moderator, transcriber and client viewer try pages and records that are not theirs, by menu and by typed address; signing out and going back shows sign-in                                                                                                      |
| `password.spec.ts`    | A forgotten password is reset from the email; the old password stops working and the other device's session ends                                                                                                                                                |
| `network.spec.ts`     | The connection drops for 8 s mid-recording; the page keeps capturing, says parts are waiting, sends them when the connection returns; nothing is lost                                                                                                           |
| `session.spec.ts`     | An administrator ends the moderator's sessions mid-recording; the page asks for a new sign-in, capture goes on, and after signing in again in another tab the waiting parts are sent; nothing is lost                                                           |

## Run locally

1. Backend on port 8000 with a database and storage configured, `EMAIL_BACKEND=file`,
   `EMAIL_FILE_DIR=<dir>`, `PUBLIC_APP_URL=http://127.0.0.1:5181`, then
   `python -m app.cli seed-dev` (needs `DEMO_PASSWORD`).
2. `E2E_ADMIN_PASSWORD=<DEMO_PASSWORD> E2E_OUTBOX=<dir> make journeys`
   (`PW_CHANNEL=chrome` uses an installed Google Chrome; `PW_EDGE=1` adds Microsoft Edge).

CI runs the same against PostgreSQL and SeaweedFS (job "User journeys in a real browser").
